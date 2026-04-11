# Spec: AgentMES

**Date:** 2026-04-11
**Status:** Approved
**Approved option:** Option C — Stub-first, swap-later, two-lane kanban
**Complexity:** Moderate–Complex (23 tasks across 6 hours of autonomous build)
**Repo:** https://github.com/benikigai/agent-mes

---

## Context

AgentMES is a manufacturing execution system for autonomous agents. It implements OpenAI's 7-stage AI-native engineering workflow (Plan → Design → Build → Test → Review → Document → Deploy) as a bipartite state machine where agents do throughput work and humans own judgment gates.

This spec covers Ben's whole-system build using a **stub-first interface-driven** approach so the demo runs end-to-end on choreographed fakes, with Vish's real Redis + Blaxel implementations swapping in additively at H6+ via single-line import changes.

The demo flows TWO tickets in parallel through TWO horizontal swim lanes:
- **TKT-001 (CODE lane):** an OAuth rate-limit fix that triggers the Stage 5 memory drift catch
- **TKT-002 (SIMPLE lane):** a status-update email about a recent incident

Both move through the same 7 stage columns. Receipts are tracked per ticket; a real GitHub PR is opened for the code ticket at Deploy.

---

## Decisions

### D1 — Stub-first, interface-driven architecture
All sponsor integrations are abstracted behind `Protocol` classes in `agent_mes/interfaces.py`. Default DI wires stubs (`agent_mes/integrations/stubs/`). Vish's real impls swap in at H6 via constructor injection. **Single-line import change.**

### D2 — Seven vertical columns, cards flow left-to-right, receipts embedded IN the card
TUI layout uses Rich's `Layout` primitive — `split_column` for header/board, then `split_row` inside board for the 7 stage columns. **Cards grow as they progress** — each StageEvent appends a line inside the card body. By the time a card lands in DEPLOY, it contains the full history of every stage. The card IS the receipt. No separate footer panel.

Both tickets share the same 7 columns and stack vertically within the current column. Type is shown via icon in the card title: `⚙ TKT-001` (CODE) and `✉ TKT-002` (SIMPLE).

### D3 — Receipts model: StageEvents embedded in the card body
Every stage transition appends a `StageEvent` to the ticket AND a corresponding rendered line inside the card. The full event list lives on `task.events`; the rendered card body is `render_card(task)` which iterates over events and produces a styled multi-line Panel. Vishal Dani's audit-trail bias satisfied (the entire history is visible on the final card); Adam Chan's "structural not heuristic" bias satisfied (events are typed StageEvent objects, not free text).

### D4 — GitHub strategy: in-memory + real PR at Deploy (Option D from chat)
No commits during the pipeline (would slow demo). The Deploy stage opens a real GitHub PR for CODE tickets, with the full receipts as the PR body. SIMPLE tickets save to `.demo/outputs/`.

### D5 — Two ticket types, same orchestrator, type-aware stage prompts
`TicketType.SIMPLE` and `TicketType.CODE`. Plan stage classifies via heuristic. Each stage branches on type to produce different artifacts. **Same pipeline + same 7 stages = generalizable MES.**

### D6 — Multi-model agent assignments
Plan: Opus 4.6. Design: Opus 4.6 + Codex + Gemini reviewer (three sub-events). Build: Codex (replay). Test: Gemini (in Blaxel sandbox). Review: Opus 4.6 + HITL gate. Document/Deploy: data sinks (Redis writes + GitHub PR). For the MVP stub, "agents" are hardcoded labels in StageEvent — no live LLM calls. Real calls are post-MVP additive.

### D7 — Rich TUI library (not Textual)
Already installed via `context-surfaces` transitive dep. Faster to ship in 6h. `Live + Layout + Panel + Table` covers everything we need.

### D8 — Codex Build replay via parsed `.cast` JSONL
Parse `recordings/codex_build_run.cast` line-by-line and write to a Rich Panel inside the Build column. Speed multiplier configurable. Real Codex run in H7 generates the recording; if it fails or takes too long, ship a hand-crafted `.cast` fixture.

---

## Three Es Options Analysis

### Option A — Original split (Ben's slice + Vish's slice in parallel)

**Approach:** Ben builds UI/orchestration/Wordware/Codex; Vish builds Redis/Blaxel; hard merge at H6 against locked function signatures.

| Criterion | Score | Reasoning |
|---|---|---|
| Elegant | 3 | Two engineers, two clear slices, but coordination tax is real |
| Efficient | 2 | Ben blocked on Vish for Stage 4/5 testing; Vish blocked on schema.py until Ben ships it |
| Effective | 3 | Works only if BOTH sides land cleanly by H6 — high integration risk |

**Architecture impact:** Two slice-owned codebases that must merge. Requires hourly sync.
**Operational risk:** If Vish slips, Ben's pipeline can't run end-to-end → no demo.
**Code churn:** ~12 files Ben + ~6 files Vish + merge conflicts in `pipeline.py`.
**Failure modes:** Vish doesn't ship → Ben has nothing to demo. Detection: Vish's hourly sync miss.
**Maintenance cost:** N/A — hackathon throwaway.

### Option B — Whole stack on real APIs from H1

**Approach:** Wire all 5 sponsor APIs live from the start, no stubs.

| Criterion | Score | Reasoning |
|---|---|---|
| Elegant | 4 | Single source of truth, no swap layer |
| Efficient | 1 | Every integration is a learning curve under time pressure |
| Effective | 2 | Demo depends on Wordware quota + Blaxel session + Redis network + Codex latency all behaving live on stage |

**Architecture impact:** Live API calls everywhere; flaky network = flaky demo.
**Operational risk:** Demo crashes mid-pitch when one of 5 external services hiccups.
**Code churn:** ~15 files but each one heavy with API client code.
**Failure modes:** Demo dies on stage. Detection: too late.
**Maintenance cost:** N/A.

### Option C — Stub-first, swap-later, two-lane kanban ⭐

**Approach:** Whole spec covers Ben + Vish slices. Default DI wires choreographed stubs. Real impls swap in additively at H6+. Demo runs identical every rehearsal.

| Criterion | Score | Reasoning |
|---|---|---|
| Elegant | 5 | Clean DI boundary, single source of truth, stubs and real impls satisfy the same Protocol |
| Efficient | 5 | Ben unblocked from Vish; Vish unblocked from Ben (only schema.py needed); /yolo can one-shot the entire system; 6h budget realistic |
| Effective | 5 | Demo certain regardless of Vish's progress; pitch ready by H6; choreographed beats hit identically every rehearsal; real APIs become pure upside |

**Architecture impact:** `interfaces.py` Protocol layer + `integrations/stubs/` directory. Real impls land in `integrations/real/` (or `vish/redis-blaxel` branch).
**Operational risk:** Stubs must be deterministic and choreographed — random stubs break the demo. Mitigation: stubs ship with seed data and deterministic state machines.
**Code churn:** 23 small files across `agent_mes/`. Each file ~50-150 LOC.
**Failure modes:**
- Stubs drift from Vish's signatures → swap fails. *Mitigation: signatures are copied verbatim from master doc.*
- Rich layout doesn't fit terminal → demo unreadable. *Mitigation: H8 layout test on demo screen.*
- Asciinema replay timing feels off → narration breaks. *Mitigation: speed multiplier + hand-crafted fallback .cast.*
**Maintenance cost:** N/A — hackathon throwaway, but the interface-driven design is genuinely production-grade.

**RECOMMENDED: Option C.** Maximizes Three Es. The only path that guarantees a working demo regardless of Vish's progress, AND lets `/yolo` build the whole thing autonomously.

---

## Critic Review (RALPLAN pattern, self-applied)

**Verdict: APPROVE with concerns.**

The critic checked: feasibility, risk blind spots, edge cases, simpler alternatives, test plan gaps. Findings:

| Concern | Severity | Resolution |
|---|---|---|
| **Stubs that look too fake will get caught by judges asking "is this real?"** | Medium | Stubs print real-looking metadata with timestamps, agent labels, and structured artifacts. The receipts panel makes it clear what's stubbed vs real. Honest narration on stage: "Blaxel sandbox API is stubbed for the rehearsal — Vish's branch swaps in real Blaxel at H6." |
| **Two parallel tickets in Rich `Live` may have race conditions on the layout** | Medium | Use a single `asyncio.Lock` around layout mutations. All stage events flow through one event bus that's the only writer to the layout. |
| **The Plan stage classifier is a 3-line heuristic — easy to break with edge case input** | Low | For the demo, only TKT-001 and TKT-002 matter. The classifier is hardcoded to recognize these two. Real classifier is post-MVP. |
| **23 tasks for /yolo is a lot — risk of mid-run drift** | Medium | Tasks are independent (DI architecture), each ≤150 LOC, each independently testable via the smoke test. /yolo can resume from the first unchecked `[ ]` if it crashes. |
| **No tests beyond smoke — risk of broken stages going undetected** | Low | A single end-to-end smoke test runs the full pipeline on both tickets and asserts each ticket has 6+ StageEvents and a final `merged` status. That's enough for a hackathon. |
| **Live Codex .cast generation in H7 may produce unusable output** | Medium | Two paths: (a) real H7 run produces the .cast, (b) hand-crafted fallback .cast committed in T08 ships with the stub Build stage. Demo never depends on H7 succeeding. |
| **Real GitHub PR at Deploy stage uses `gh` CLI which requires auth** | Low | `gh auth status` confirms benikigai is logged in (verified during repo creation). PR creation tested in T19 (Deploy stage task). |

**No critical flaws.** Proceed.

---

## Architecture diagram

Seven vertical stage columns. Cards flow left to right. **Receipts are embedded inside the card body** — each stage event appends a line, so by the time a card lands in DEPLOY, it contains its full history. Both tickets share the same column flow and stack vertically inside the current column. Type icons in the title: `⚙` for CODE, `✉` for SIMPLE.

```
┌─ AgentMES TUI (Rich Live, refresh 10/s) ───────────────────────────────────┐
├──────────┬─────────┬────────┬───────┬────────┬──────────┬─────────────────┤
│   PLAN   │ DESIGN  │ BUILD  │  TEST │ REVIEW │ DOCUMENT │ DEPLOY/MAINTAIN │
├──────────┼─────────┼────────┼───────┼────────┼──────────┼─────────────────┤
│          │         │        │       │        │          │ ┌[⚙ TKT-001]┐  │
│          │         │        │       │        │          │ │OAuth fix   │  │
│          │         │        │       │        │          │ │✓ PLAN Opus │  │
│          │         │        │       │        │          │ │✓ DSGN Opus │  │
│          │         │        │       │        │          │ │✓ DSGN Codex│  │
│          │         │        │       │        │          │ │✓ DSGN Gem  │  │
│          │         │        │       │        │          │ │✓ BLD  Codex│  │
│          │         │        │       │        │          │ │✓ TST  i1 F │  │
│          │         │        │       │        │          │ │✗ TST  i2 K │  │
│          │         │        │       │        │          │ │✓ TST  i3 P │  │
│          │         │        │       │        │          │ │⚠ REV  DRIFT│  │
│          │         │        │       │        │          │ │✓ REV  HUMAN│  │
│          │         │        │       │        │          │ │✓ DOC  Redis│  │
│          │         │        │       │        │          │ │✓ DEP  PR#12│  │
│          │         │        │       │        │          │ └────────────┘  │
│          │         │        │       │        │          │ ┌[✉ TKT-002]┐  │
│          │         │        │       │        │          │ │Status email│  │
│          │         │        │       │        │          │ │✓ PLAN Opus │  │
│          │         │        │       │        │          │ │✓ DSGN Opus │  │
│          │         │        │       │        │          │ │✓ BLD  Codex│  │
│          │         │        │       │        │          │ │✓ TST  Gem  │  │
│          │         │        │       │        │          │ │✓ REV  Opus │  │
│          │         │        │       │        │          │ │✓ DOC  Redis│  │
│          │         │        │       │        │          │ │✓ DEP  email│  │
│          │         │        │       │        │          │ └────────────┘  │
└──────────┴─────────┴────────┴───────┴────────┴──────────┴─────────────────┘
```

**Card growth pattern.** When TKT-001 is in PLAN, the card has 2 lines (title + first event). When it moves to DESIGN, it has 5 lines. By DEPLOY, it has 14+ lines showing the full receipts. The natural visual narrative is: cards on the left are short, cards on the right are tall. **The card body IS the audit trail.**

---

## Tasks

### Task 1: Project scaffolding
**Objective:** Stand up the Python package structure, build/test tooling, and entrypoints so subsequent tasks have a place to drop files.
**Complexity:** Simple
**Dependencies:** None
**Files to change:**
- `pyproject.toml` (new)
- `Makefile` (new)
- `agent_mes/__init__.py` (new)
- `agent_mes/integrations/__init__.py` (new)
- `agent_mes/integrations/stubs/__init__.py` (new)
- `agent_mes/stages/__init__.py` (new)
- `agent_mes/ui/__init__.py` (new)
- `agent_mes/demo/__init__.py` (new)
- `tests/__init__.py` (new)
- `recordings/.gitkeep` (new)
- `.demo/.gitkeep` (new)
**Acceptance criteria:**
- `python -m agent_mes --help` runs (even if it just prints usage)
- `make test` runs pytest with no collected tests successfully
- `pyproject.toml` declares deps: `rich`, `pydantic>=2`, `httpx`, `typer`, `pytest`
**Test plan:**
- Smoke: `python -c "import agent_mes; print(agent_mes.__name__)"` returns `agent_mes`
- Smoke: `make test` exits 0
**Rollback plan:** `rm -rf agent_mes/ tests/ pyproject.toml Makefile recordings .demo`
**Blast radius:** None — fresh package, no existing code touched
**Research needed:** No

---

### Task 2: agent_mes/schema.py — Pydantic models
**Objective:** Lock the MESTask schema and supporting types. This is the contract Vish builds against — must match the master doc verbatim.
**Complexity:** Moderate
**Dependencies:** Task 1
**Files to change:**
- `agent_mes/schema.py` (new)
**Acceptance criteria:**
- Defines: `TicketType` (StrEnum: SIMPLE, CODE), `StageEnum` (PLAN, DESIGN, BUILD, TEST, REVIEW, DOCUMENT, DEPLOY), `StageResult` (PASS, FAIL, BLOCK_FOR_HUMAN, KILLED)
- Defines: `BlastRadius` (allowed_paths: list[str], network_egress: bool, max_cost_usd: float)
- Defines: `AcceptanceCriterion` (description: str, machine_check: str)
- Defines: `MemoryProvenance` (text: str, confidence: float, source: str, retrieved_at: datetime)
- Defines: `Artifact` (type: Literal[...], ref: str, summary: str)
- Defines: `StageEvent` (timestamp, stage, agent, action, metadata: dict, artifacts: list[Artifact])
- Defines: `HumanGate` (stage: StageEnum, prompt: str, approved: bool|None, approver: str|None)
- Defines: `MESTask` (id: str, type: TicketType, intent: str, raw_input: str, requester: str, source: str, blast_radius: BlastRadius, acceptance_criteria: list[AcceptanceCriterion], context_bundle: dict, memory_provenance: list[MemoryProvenance], events: list[StageEvent], human_gates: list[HumanGate], current_stage: StageEnum, status: Literal["pending","running","blocked","merged","killed"])
- All models inherit from `pydantic.BaseModel` (Pydantic v2)
- `MESTask.model_validate({...})` round-trips through `model_dump()`
**Test plan:**
- Unit: `tests/test_schema.py` — instantiate a minimal MESTask, dump, reload, assert equal
- Unit: enum values match the master doc spelling exactly
**Rollback plan:** `rm agent_mes/schema.py`
**Blast radius:** Vish's branch depends on this verbatim; changing it later requires Vish announcement
**Research needed:** No

---

### Task 3: agent_mes/interfaces.py — Protocol classes
**Objective:** Lock the swap-able backend contracts (Vish's three integration files) as Python `Protocol` classes. Stubs and real impls both satisfy these.
**Complexity:** Simple
**Dependencies:** Task 2
**Files to change:**
- `agent_mes/interfaces.py` (new)
**Acceptance criteria:**
- Defines `RedisMemoryProtocol` with `hydrate`, `cross_check`, `write_lesson`, `seed_demo_memories`
- Defines `ContextRetrieverProtocol` with `query_entity`, `list_related`, `verify_claim`
- Defines `BlaxelVerifierProtocol` with `create_sandbox`, `run_check`, `self_heal_loop`, `detect_egress_violation`
- Defines `WordwarePlannerProtocol` with `plan_from_slack(raw_text, requester, channel) -> dict`
- Defines `CodexBuilderProtocol` with `build(task) -> AsyncIterator[str]` (yields lines from the cast)
- All async, all signatures verbatim from master doc
**Test plan:**
- Unit: import all protocols, check they're recognized by `isinstance(obj, Protocol)`
**Rollback plan:** `rm agent_mes/interfaces.py`
**Blast radius:** All stages and stubs depend on these
**Research needed:** No

---

### Task 4: agent_mes/integrations/stubs/redis_memory.py
**Objective:** Choreographed stub of `RedisMemoryProtocol`. Returns deterministic seeded data so the demo hits the same beats every rehearsal.
**Complexity:** Moderate
**Dependencies:** Task 3
**Files to change:**
- `agent_mes/integrations/stubs/redis_memory.py` (new)
**Acceptance criteria:**
- `class StubRedisMemory` implements `RedisMemoryProtocol`
- `hydrate(query)` returns 3 fixture memories from `agent_mes/demo/seed_memories.py` filtered by string match in query
- `cross_check(claim)` returns `{contradicted: True, supporting: [], contradicting: [{...}]}` if claim contains "auth rate limit"; else returns `{contradicted: False, ...}`
- `write_lesson(text, topics, user_id, negative_constraint)` appends to `.demo/memory_log.jsonl` and returns a fake `mem_NNNN` id
- `seed_demo_memories(fixtures)` is a no-op (fixtures are loaded from seed_memories.py)
**Test plan:**
- Unit: `tests/test_stub_redis_memory.py` — call hydrate with "auth", assert 3 memories returned, assert one has confidence 0.9 and contains "rate limiter"
- Unit: cross_check with "auth rate limit fixed" returns contradicted=True
**Rollback plan:** `rm agent_mes/integrations/stubs/redis_memory.py`
**Blast radius:** Stages 2, 5, 6, 7 depend on this
**Research needed:** No

---

### Task 5: agent_mes/integrations/stubs/context_retriever.py
**Objective:** Choreographed stub of `ContextRetrieverProtocol`. Returns the seeded Heliograph entities so Stage 2 hydration and Stage 5 verification look real.
**Complexity:** Moderate
**Dependencies:** Task 3
**Files to change:**
- `agent_mes/integrations/stubs/context_retriever.py` (new)
**Acceptance criteria:**
- `class StubContextRetriever` implements `ContextRetrieverProtocol`
- `query_entity(entity_type, entity_id)` returns the seeded entity from a hardcoded fixture dict (Service, User, Incident, Ticket)
- `list_related(entity_type, filter_dict)` returns the matching list from the fixtures
- `verify_claim(claim, entity_type)` returns `{verified: False, actual: {endpoint: "/v1/login"}, discrepancy: "endpoint mismatch /v1/login vs /v2/oauth"}` for the auth rate limiter claim; `{verified: True, ...}` otherwise
**Test plan:**
- Unit: `tests/test_stub_context_retriever.py` — verify_claim with the auth rate limiter claim returns verified=False with the discrepancy field set
**Rollback plan:** `rm agent_mes/integrations/stubs/context_retriever.py`
**Blast radius:** Stages 2, 5 depend on this
**Research needed:** No

---

### Task 6: agent_mes/integrations/stubs/blaxel.py
**Objective:** Choreographed stub of `BlaxelVerifierProtocol`. Implements the kill-and-self-heal loop deterministically: iter 1 fails on import, iter 2 fails on egress kill (returns BLAST_RADIUS_VIOLATION), iter 3 passes.
**Complexity:** Complex
**Dependencies:** Task 3
**Files to change:**
- `agent_mes/integrations/stubs/blaxel.py` (new)
**Acceptance criteria:**
- `class StubBlaxelVerifier` implements `BlaxelVerifierProtocol`
- `create_sandbox(task_id, blast_radius)` returns a `StubSandbox` object with id, state="running"
- `run_check(sandbox, machine_check)` simulates a 200ms run via `asyncio.sleep(0.2)`; returns based on `sandbox.iteration` counter
- `detect_egress_violation(sandbox)` returns `{violated_at: now, destination: "evil.example.com", killed_in_ms: 23}` on iteration 2; None otherwise
- `self_heal_loop(sandbox, code_diff, checks, max_iterations=3)` orchestrates the 3-iteration sequence and returns `{iterations: [...], final_status: "pass"}` after iter 3
- Each iteration emits a status message that the stage can capture
**Test plan:**
- Unit: `tests/test_stub_blaxel.py` — self_heal_loop with 3 iterations, assert iter 1 fail, iter 2 egress kill, iter 3 pass
- Unit: detect_egress_violation on iter 2 returns the violation dict
**Rollback plan:** `rm agent_mes/integrations/stubs/blaxel.py`
**Blast radius:** Stage 4 depends on this. THE demo gold moment.
**Research needed:** No

---

### Task 7: agent_mes/integrations/wordware.py — stub + real flag
**Objective:** Wordware planner with stub mode by default and a real-mode flag for when the WordApp flow is built. Stub returns a hardcoded MESTask first-stage payload from `demo/fake_slack.py`.
**Complexity:** Simple
**Dependencies:** Task 3, Task 9
**Files to change:**
- `agent_mes/integrations/wordware.py` (new)
**Acceptance criteria:**
- `class WordwarePlanner` implements `WordwarePlannerProtocol`
- Constructor takes `mode: Literal["stub","real"] = "stub"` and optional `flow_url`, `api_key`
- In stub mode, `plan_from_slack(raw_text, requester, channel)` returns the corresponding fixture from `demo/fake_slack.py`
- In real mode, POSTs to `flow_url` with the payload and parses the response (real impl is a placeholder for H7)
**Test plan:**
- Unit: `tests/test_wordware.py` — stub mode returns the TKT-001 fixture for the OAuth message, TKT-002 for the email message
**Rollback plan:** `rm agent_mes/integrations/wordware.py`
**Blast radius:** Stage 1 depends on this
**Research needed:** No

---

### Task 8: agent_mes/integrations/codex.py — asciinema replay player
**Objective:** Codex builder that streams a `.cast` file line-by-line into a Rich panel with controlled playback speed. Used by Stage 3 in replay mode.
**Complexity:** Moderate
**Dependencies:** Task 3
**Files to change:**
- `agent_mes/integrations/codex.py` (new)
- `recordings/codex_build_run.cast` (new — hand-crafted fallback fixture)
**Acceptance criteria:**
- `class CodexReplayBuilder` implements `CodexBuilderProtocol`
- Constructor takes `cast_path: Path` and `speed: float = 8.0`
- `build(task)` is an async generator that yields output lines from the cast at scaled timing
- Hand-crafted `recordings/codex_build_run.cast` has ~30 lines of plausible Codex output (file edits, test runs, "writing PR description...")
- Cast format is JSONL: `[timestamp, "o", "text"]` per line, with a header line `{"version": 2, "width": 100, "height": 30}`
**Test plan:**
- Unit: `tests/test_codex.py` — call build() and collect 5 lines, assert non-empty strings
- Smoke: parse the fixture .cast, assert valid JSONL
**Rollback plan:** `rm agent_mes/integrations/codex.py recordings/codex_build_run.cast`
**Blast radius:** Stage 3 depends on this
**Research needed:** No

---

### Task 9: agent_mes/demo/* — fixtures
**Objective:** Ship the demo data: the fake Slack messages (TKT-001 + TKT-002), the seeded memory pool, and the poison payload module.
**Complexity:** Simple
**Dependencies:** Task 2
**Files to change:**
- `agent_mes/demo/fake_slack.py` (new) — TKT-001 (OAuth fix) + TKT-002 (status email)
- `agent_mes/demo/seed_memories.py` (new) — 10 fixture memories incl. the adversary "auth rate limiter fixed last month" claim
- `agent_mes/demo/poison_payload.py` (new) — fake module that does `requests.get("http://evil.example.com")` on import
- `agent_mes/demo/seed_entities.py` (new) — Heliograph fixtures (4 services, 8 users, 12 incidents, 6 tickets) for the Context Retriever stub
**Acceptance criteria:**
- TKT-001 raw text mentions OAuth, /v2, rate limit; classified as CODE
- TKT-002 raw text is "send a status update email about the auth incident"; classified as SIMPLE
- Seed memories include exactly one with `text="we already fixed the auth rate limiter on the login service last month"` and `confidence=0.9`
- Heliograph entities include Incident `inc_113` with `endpoint="/v1/login"` and Ticket `tkt_982` with `body` mentioning `/v2/oauth`
- Poison payload module raises ImportError when imported (so iter 1 of self-heal fails on import)
**Test plan:**
- Unit: `tests/test_demo_fixtures.py` — load all fixtures, assert TKT-001 type=CODE, TKT-002 type=SIMPLE, seed_memories has 10 entries
**Rollback plan:** `rm -rf agent_mes/demo/*.py`
**Blast radius:** All stub stages depend on these fixtures
**Research needed:** No

---

### Task 10: agent_mes/stages/base.py — BaseStage abstract class
**Objective:** Common interface for all 7 stage classes. Each stage takes a task, executes, emits StageEvent(s), advances the task's `current_stage`.
**Complexity:** Simple
**Dependencies:** Task 2
**Files to change:**
- `agent_mes/stages/base.py` (new)
**Acceptance criteria:**
- `class BaseStage(ABC)` with `STAGE: StageEnum` (subclass overrides) and abstract `async def execute(self, task: MESTask) -> list[StageEvent]`
- Provides `_emit_event(stage, agent, action, metadata, artifacts)` helper
- Provides `_branch_by_type(task)` helper that returns "simple" or "code"
**Test plan:**
- Unit: subclass returns events, base class advances task.current_stage
**Rollback plan:** `rm agent_mes/stages/base.py`
**Blast radius:** All stage classes depend on this
**Research needed:** No

---

### Task 11: agent_mes/stages/plan.py
**Objective:** Plan stage. Calls Wordware to translate raw input → MESTask first-stage payload. Classifies ticket type via heuristic. Records HumanGate (auto-approves with 2s pause for visual effect).
**Complexity:** Simple
**Dependencies:** Task 7, 9, 10
**Files to change:**
- `agent_mes/stages/plan.py` (new)
**Acceptance criteria:**
- `class PlanStage(BaseStage)` with `STAGE = StageEnum.PLAN`, `AGENT = "Opus 4.6"`
- Constructor takes `wordware: WordwarePlannerProtocol`
- `execute(task)` calls wordware.plan_from_slack, populates task.intent / task.acceptance_criteria / task.blast_radius, classifies type via keyword heuristic
- Emits 1 StageEvent with action="classified=<type>, ac=<count>, blast=<scope>"
- Records HumanGate with auto-approval after 2s
**Test plan:**
- Unit: `tests/test_plan_stage.py` — TKT-001 → CODE, TKT-002 → SIMPLE
**Rollback plan:** `rm agent_mes/stages/plan.py`
**Blast radius:** Pipeline depends on this
**Research needed:** No

---

### Task 12: agent_mes/stages/design.py
**Objective:** Design stage. Hydrates context_bundle (via Context Retriever) and memory_provenance (via Redis Memory). Emits THREE StageEvents — one each for Opus, Codex, Gemini sub-agents.
**Complexity:** Moderate
**Dependencies:** Task 4, 5, 10
**Files to change:**
- `agent_mes/stages/design.py` (new)
**Acceptance criteria:**
- `class DesignStage(BaseStage)` with `STAGE = StageEnum.DESIGN`, `AGENTS = ["Opus 4.6", "Codex", "Gemini"]`
- Constructor takes `redis: RedisMemoryProtocol`, `context: ContextRetrieverProtocol`
- `execute(task)` calls redis.hydrate and context.query_entity in parallel via `asyncio.gather`
- Populates task.memory_provenance and task.context_bundle
- Emits 3 StageEvents: Opus (sketched architecture), Codex (scaffolded files), Gemini (reviewed sketch)
- Each event has typed metadata (memory_count, entity_count)
**Test plan:**
- Unit: `tests/test_design_stage.py` — for TKT-001, asserts 3 events emitted, asserts memory_provenance has 3 entries
**Rollback plan:** `rm agent_mes/stages/design.py`
**Blast radius:** Stages 5, 6 depend on the hydrated state
**Research needed:** No

---

### Task 13: agent_mes/stages/build.py
**Objective:** Build stage. For CODE tickets, replays the Codex .cast through the Build column. For SIMPLE tickets, drafts the email body via a hardcoded template.
**Complexity:** Moderate
**Dependencies:** Task 8, 10
**Files to change:**
- `agent_mes/stages/build.py` (new)
**Acceptance criteria:**
- `class BuildStage(BaseStage)` with `STAGE = StageEnum.BUILD`, `AGENT = "Codex"`
- Constructor takes `codex: CodexBuilderProtocol`
- For CODE: streams cast lines via codex.build, captures the final "diff summary", emits StageEvent with metadata `{lines_added, lines_removed, files_touched}`
- For SIMPLE: returns a hardcoded email draft (subject, body), emits StageEvent with metadata `{recipient, word_count}`
- Both types produce an Artifact (type=file for code, type=email for simple)
**Test plan:**
- Unit: `tests/test_build_stage.py` — TKT-001 emits diff metadata, TKT-002 emits email metadata
**Rollback plan:** `rm agent_mes/stages/build.py`
**Blast radius:** Stage 4 (Test) depends on the build output
**Research needed:** No

---

### Task 14: agent_mes/stages/test.py
**Objective:** Test stage. For CODE tickets, runs the Blaxel self-heal loop (the demo gold moment). For SIMPLE tickets, runs Gemini's "tone + grammar" review (stubbed as a 1s pause + pass).
**Complexity:** Complex
**Dependencies:** Task 6, 9, 10
**Files to change:**
- `agent_mes/stages/test.py` (new)
**Acceptance criteria:**
- `class TestStage(BaseStage)` with `STAGE = StageEnum.TEST`, `AGENT = "Gemini"` (with Blaxel sub-agent for code)
- Constructor takes `blaxel: BlaxelVerifierProtocol`
- For CODE: calls blaxel.create_sandbox, then blaxel.self_heal_loop with 3 iterations; emits ONE StageEvent per iteration (action: "iter N: <result>")
- The egress violation iteration emits StageEvent with action "iter 2: KILLED — egress to evil.example.com (23ms)" and metadata `{violation: {...}}`
- For SIMPLE: 1s pause, single StageEvent action="grammar+tone OK"
- Stage status after the loop: PASS (advances) or BLOCK_FOR_HUMAN (stops)
**Test plan:**
- Unit: `tests/test_test_stage.py` — TKT-001 produces 3 iteration events with iter 2 marked KILLED; TKT-002 produces 1 event
**Rollback plan:** `rm agent_mes/stages/test.py`
**Blast radius:** THE demo gold moment. Critical.
**Research needed:** No

---

### Task 15: agent_mes/stages/review.py
**Objective:** Review stage. Cross-checks every memory_provenance entry against ground truth (via Context Retriever). Catches the memory drift on TKT-001. Emits HumanGate (REAL gate — pauses for actual keyboard input).
**Complexity:** Complex
**Dependencies:** Task 4, 5, 10
**Files to change:**
- `agent_mes/stages/review.py` (new)
**Acceptance criteria:**
- `class ReviewStage(BaseStage)` with `STAGE = StageEnum.REVIEW`, `AGENT = "Opus 4.6"`
- Constructor takes `redis: RedisMemoryProtocol`, `context: ContextRetrieverProtocol`
- For each memory in task.memory_provenance: calls context.verify_claim — if verified=False, emits StageEvent action="DRIFT: memory says X, ground truth says Y" and drops memory.confidence
- For TKT-001 (the auth rate limiter case): the drift catch fires; emits HumanGate event action="awaiting approval... [APPROVE]"
- For TKT-002 (email): no drift; auto-approves
- HumanGate is REAL — `await asyncio.get_event_loop().run_in_executor(None, input, "Approve TKT-001? [y/n] ")` — this is the moment Ben presses APPROVE on stage
**Test plan:**
- Unit: `tests/test_review_stage.py` — TKT-001 emits DRIFT event, TKT-002 does not. (Skip the input() in tests via env flag)
**Rollback plan:** `rm agent_mes/stages/review.py`
**Blast radius:** THE second demo gold moment. Critical.
**Research needed:** No

---

### Task 16: agent_mes/stages/document.py
**Objective:** Document stage. Generates a decision log from the StageEvents and writes it to Redis Memory as a long-term lesson.
**Complexity:** Simple
**Dependencies:** Task 4, 10
**Files to change:**
- `agent_mes/stages/document.py` (new)
**Acceptance criteria:**
- `class DocumentStage(BaseStage)` with `STAGE = StageEnum.DOCUMENT`, `AGENT = "Redis"` (data sink, no LLM)
- Constructor takes `redis: RedisMemoryProtocol`
- `execute(task)` builds a decision log string from task.events, calls redis.write_lesson with topics=[task.type, "task_completion"] and negative_constraint=True for the corrected memory
- Emits StageEvent with action="lesson written: <id>" and Artifact(type="memory", ref=lesson_id)
**Test plan:**
- Unit: `tests/test_document_stage.py` — execute returns 1 event with memory artifact
**Rollback plan:** `rm agent_mes/stages/document.py`
**Blast radius:** Stage 7 follows
**Research needed:** No

---

### Task 17: agent_mes/stages/deploy.py
**Objective:** Deploy stage. For CODE tickets, opens a real GitHub PR with the receipts as the PR body. For SIMPLE tickets, writes the email draft to `.demo/outputs/`. Logs a monitoring breadcrumb to Redis.
**Complexity:** Moderate
**Dependencies:** Task 4, 10
**Files to change:**
- `agent_mes/stages/deploy.py` (new)
**Acceptance criteria:**
- `class DeployStage(BaseStage)` with `STAGE = StageEnum.DEPLOY`, `AGENT = "GitHub+Blaxel+Redis"`
- Constructor takes `redis: RedisMemoryProtocol`, optional `github_repo: str`
- For CODE: builds a PR body from task.events, calls `gh pr create --body-file <tmpfile> --title "AgentMES: <task.intent>"` via subprocess; captures PR URL
- For SIMPLE: writes `.demo/outputs/email-{task.id}.md` with the email body
- Both: writes a deploy breadcrumb to Redis via redis.write_lesson
- Both: emits StageEvent with action="PR <url>" or "wrote email to <path>" and Artifact (type=pr or email)
- Sets task.status = "merged"
- Has a `dry_run: bool = False` flag — if True, prints the gh command instead of running it (for tests + safety)
**Test plan:**
- Unit: `tests/test_deploy_stage.py` — TKT-001 dry_run=True prints gh command, TKT-002 writes file to tmpdir
**Rollback plan:** `rm agent_mes/stages/deploy.py`
**Blast radius:** Real PRs created against the repo. Use dry_run=False ONLY in real demo runs.
**Research needed:** No

---

### Task 18: agent_mes/pipeline.py — orchestrator
**Objective:** The Pipeline class wires all 7 stages, drives a task through them in sequence, and emits a stream of events for the dashboard to consume.
**Complexity:** Moderate
**Dependencies:** Tasks 11-17
**Files to change:**
- `agent_mes/pipeline.py` (new)
**Acceptance criteria:**
- `class Pipeline` with constructor taking all 7 stage instances + an `events_callback: Callable[[StageEvent], None]`
- `async def run(self, task: MESTask) -> MESTask` runs each stage in order, calls callback after each event
- `async def run_parallel(self, tasks: list[MESTask]) -> list[MESTask]` runs multiple tasks via `asyncio.gather` (used for the 2-ticket demo)
- Handles BLOCK_FOR_HUMAN by pausing the task (Review stage's HumanGate input())
- Catches exceptions per stage and converts to StageResult.FAIL events instead of crashing
**Test plan:**
- Unit: `tests/test_pipeline.py` — full pipeline run on TKT-002 (no human gate path) produces 7+ events and ends with status="merged"
- Integration: run_parallel with TKT-001 and TKT-002, assert both end with status="merged" (skip Review's input() via env flag)
**Rollback plan:** `rm agent_mes/pipeline.py`
**Blast radius:** This is the central nervous system. Test thoroughly.
**Research needed:** No

---

### Task 19: agent_mes/ui/lanes.py — Rich Layout + detailed-changelog card render
**Objective:** The 7-column vertical kanban layout PLUS a rich card renderer that produces a **running detailed changelog inside each card**. Each StageEvent contributes 1-3 lines: action line + key metadata fields + artifact references. By the time a card lands in DEPLOY, the body shows the complete structured history of every stage with typed fields (not just terse symbols).
**Complexity:** Moderate
**Dependencies:** Task 1
**Files to change:**
- `agent_mes/ui/lanes.py` (new — name kept for clarity even though "lanes" are now vertical columns)
**Acceptance criteria:**
- `def build_layout() -> Layout` returns a Rich Layout with named regions: header (size=3), then board split_row into 7 columns (plan, design, build, test, review, document, deploy)
- `def render_card(task: MESTask) -> Panel` returns a styled Panel rendering a **detailed changelog**:
  - Title: `f"{'⚙' if task.type == 'code' else '✉'} {task.id}"`
  - Body line 1: `task.intent` (bold)
  - Body line 2: separator
  - Then for each `StageEnum` that has events on the task: a `━ STAGE ━` header line (cyan bold), followed by each event:
    - Main line: `f"{symbol} [{event.agent}] {event.action}"` where symbol = ✓ PASS, ✗ KILLED/FAIL, ⚠ DRIFT/WARN, ⏳ RUN
    - Indented metadata lines: `f"   {key}: {val}"` for each non-internal key in `event.metadata` (skip `status`, `ticket_id`)
    - Indented artifact lines: `f"   → {artifact.type}: {artifact.ref}"` (green)
  - border_style: blue=running, yellow=blocked, green=merged, red=killed
- Example final card body for TKT-001 (CODE) is ~30 lines tall and includes lines like `iter 2: KILLED`, `egress: evil.example.com`, `killed_in_ms: 23`, `→ pr: github.com/benikigai/agent-mes/pull/12`
- Example final card body for TKT-002 (SIMPLE) is ~15 lines tall
- `def render_column(tasks_in_col: list[MESTask]) -> Panel` returns a Panel containing a Group of card Panels stacked vertically (with a 1-line gap between cards)
- Default styling: rich Console + Panel + Group + Text
**Test plan:**
- Unit: `tests/test_lanes.py` — build_layout returns Layout with 7 column regions
- Unit: render_card on a task with 1 event in PLAN produces a Panel whose body contains "━ PLAN ━" header, the event action, and at least one metadata line
- Unit: render_card on a fully-completed TKT-001 (with all 7 stages of events) produces a Panel with at least 25 body lines
**Rollback plan:** `rm agent_mes/ui/lanes.py`
**Blast radius:** Dashboard depends on this; this IS the "detailed changelog inside the card" Ben requested
**Research needed:** No

---

### Task 20: agent_mes/ui/dashboard.py — live dashboard
**Objective:** The Dashboard class subscribes to pipeline events and updates the layout in real time. Uses `rich.live.Live` with a refresh rate of 10/s. **No separate receipts panel** — receipts are embedded inside each card via `render_card()`. When a stage event fires, the card is re-rendered (with the new line appended) and placed in its current column.
**Complexity:** Complex
**Dependencies:** Tasks 18, 19
**Files to change:**
- `agent_mes/ui/dashboard.py` (new)
**Acceptance criteria:**
- `class Dashboard` constructor takes a layout from `lanes.build_layout()` and a list of MESTask references
- `on_event(event: StageEvent, task: MESTask)` is the callback registered with the pipeline. It (1) holds the asyncio.Lock, (2) re-renders ALL columns by grouping tasks by current_stage and calling render_column, (3) updates each layout region with the new content
- `async def run(self, pipeline: Pipeline, tasks: list[MESTask])` wraps in `with Live(layout, refresh_per_second=10, console=Console()):` and runs `pipeline.run_parallel(tasks)`
- Cards naturally grow as events accumulate inside `task.events` (the render function reads from there)
- When a card transitions to a new stage, it disappears from the old column and appears in the new column on the next render
- Single asyncio.Lock around layout mutations to serialize parallel updates
- Demo terminal sized 100×60 minimum (header check + warning if too small)
**Test plan:**
- Smoke: `AGENTMES_AUTO_APPROVE=1 python -m agent_mes demo --dry-run` runs the full dashboard with both tickets, both reach DEPLOY, exits cleanly in <60s
- Smoke: pipe stdout to a file and assert no exceptions
**Rollback plan:** `rm agent_mes/ui/dashboard.py`
**Blast radius:** This IS the demo. Critical.
**Research needed:** No

---

### Task 21: agent_mes/cli.py — CLI entrypoint
**Objective:** The `agent-mes` CLI. `agent-mes demo` runs the full demo. `agent-mes --help` shows usage. Wires up all the stub DI by default.
**Complexity:** Simple
**Dependencies:** Task 20
**Files to change:**
- `agent_mes/cli.py` (new)
- `agent_mes/__main__.py` (new — entrypoint for `python -m agent_mes`)
**Acceptance criteria:**
- Uses `typer` for CLI
- `agent-mes demo` constructs StubRedisMemory, StubContextRetriever, StubBlaxelVerifier, WordwarePlanner(stub), CodexReplayBuilder, all 7 stages, Pipeline, Dashboard, then runs with both fixture tickets in parallel
- `agent-mes demo --real-redis` swaps in the real Redis (placeholder for Vish's branch — falls back to stub if `redis_memory.real` not importable)
- `agent-mes demo --dry-run` passes dry_run=True to Deploy stage so no real PRs are created
- `agent-mes --help` works
**Test plan:**
- Smoke: `agent-mes --help` exits 0
- Smoke: `agent-mes demo --dry-run` runs both tickets to completion in <60s
**Rollback plan:** `rm agent_mes/cli.py agent_mes/__main__.py`
**Blast radius:** Entry point — test before any demo run
**Research needed:** No

---

### Task 22: tests/test_smoke.py — end-to-end smoke test
**Objective:** A single integration test that runs the full pipeline on both tickets via stubs and asserts the choreographed beats hit. This is the gate for "demo is ready."
**Complexity:** Simple
**Dependencies:** Task 21
**Files to change:**
- `tests/test_smoke.py` (new)
**Acceptance criteria:**
- Runs Pipeline.run_parallel with TKT-001 and TKT-002
- Asserts TKT-001 has at least 10 StageEvents (Plan + 3xDesign + Build + 3xTest iterations + Review drift + Review human + Document + Deploy)
- Asserts TKT-001 has a TestStage iter 2 event with `metadata.violation.destination == "evil.example.com"`
- Asserts TKT-001 has a ReviewStage event with action containing "DRIFT"
- Asserts TKT-002 has at least 7 StageEvents (one per stage)
- Asserts both tickets end with status="merged"
- Skips the Review stage's `input()` via `AGENTMES_AUTO_APPROVE=1` env var
- Uses dry_run=True for Deploy (no real PRs)
- Completes in <30 seconds
**Test plan:**
- Smoke: `make test` runs this and exits 0
**Rollback plan:** `rm tests/test_smoke.py`
**Blast radius:** This is the gate. If this fails, the demo is broken.
**Research needed:** No

---

### Task 23: README + polish
**Objective:** Update README.md with the AgentMES pitch, install + run instructions, sponsor credits, judge intel summary. Add a screenshot (text capture) of the demo running.
**Complexity:** Simple
**Dependencies:** Task 22
**Files to change:**
- `README.md` (overwrite)
- `docs/demo-screenshot.txt` (new — capture of the dashboard running)
**Acceptance criteria:**
- README has elevator pitch (1 paragraph), install (`pip install -e .` from venv), run (`agent-mes demo`), architecture diagram (the 2-lane × 7-column ASCII), sponsor credit line ("Built with Wordware, Blaxel, OpenAI Codex, Redis Agent Memory Server, and Redis Context Surfaces"), and a link to the spec
- Screenshot is a literal text capture of the dashboard at the moment of the Blaxel kill (iter 2) — captured manually after T22 passes
- Submission checklist appended at the end
**Test plan:**
- Smoke: README opens and renders on github.com
**Rollback plan:** `git checkout README.md`
**Blast radius:** None — docs only
**Research needed:** No

---

## Demo display strategy

**Recommendation: Localhost terminal projected, with asciinema recording as backup. NOT Vercel.**

| Option | Approach | Verdict |
|---|---|---|
| **A. Localhost terminal projected to demo TV** ⭐ | Run `agent-mes demo` on Ben's laptop, project the screen output | **Best** — native, fast, no extra dev work, judges expect terminal demos at engineering hackathons |
| **B. Localhost + asciinema backup recording** ⭐ | Same as A + record a known-good run as `recordings/full-demo.cast` | **Best paired with A** — backup if live demo crashes |
| C. Vercel web wrapper (xterm.js + WebSocket bridge) | Wrap the TUI in a web view | **Reject** — 4-6h additional dev work for marginal benefit; rich terminal output may not render perfectly in browser; we don't have the time |
| D. tmate live share | Give judges a tmate URL they can connect to | **Reject** — requires judge action; demo dependency on Ben's laptop |

**The two surfaces:**

1. **Live demo:** Ben's laptop, terminal at 100×60, projected to the demo TV. `agent-mes demo` runs the full pipeline with both tickets in parallel. Total runtime ~30-45 seconds. Ben narrates while it runs.

2. **Submission URL:** the GitHub repo (https://github.com/benikigai/agent-mes) is the official artifact. README contains the elevator pitch, install instructions, the architecture diagram, the asciinema cast embedded via `<asciinema-player>` or linked to https://asciinema.org. **This is what judges revisit after the live pitch.**

**Asciinema strategy.** Two `.cast` files:
- `recordings/codex_build_run.cast` — used INSIDE the Build column during the demo (Codex output replay, scrubbed to fit ~15 sec)
- `recordings/full-demo.cast` — full top-to-bottom demo recording captured during H7 polish, used as the backup if the live demo crashes (Ben plays it back instead of running live)

**Vercel as a SECONDARY surface (optional, post-MVP):** if there's leftover time at H8, we can throw up a tiny Vercel landing page at `agentmes.vercel.app` that links to the GitHub repo, embeds the asciinema player, and lists the sponsor credits. This is a 30-min job with `npx create-next-app` + a single page. It's NOT the demo — it's a polished submission landing page. **Build only if H8 has spare budget.**

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Stubs drift from Vish's signatures → swap fails at H6 | High | Signatures are copied verbatim from master doc into `interfaces.py` (Task 3); Vish reviews `interfaces.py` before starting |
| Rich Live race conditions on the layout with 2 parallel tasks | Medium | Single asyncio.Lock around layout mutations; all events flow through one event bus (Task 20) |
| Asciinema replay timing feels off in demo | Medium | Speed multiplier configurable; hand-crafted .cast fallback ships with Task 8 |
| Real GitHub PR fails on stage (gh auth, rate limit) | Low | dry_run=True flag for rehearsals; only run real PRs in the actual demo |
| Plan stage classifier breaks on edge case input | Low | Hardcoded to recognize TKT-001 and TKT-002; real classifier is post-MVP |
| Demo terminal too small for 100×30 layout | Medium | H8 layout test on demo display; fallback single-lane mode if needed |
| 23 tasks for /yolo is a lot — mid-run drift | Medium | Tasks are independent (DI architecture); /yolo can resume from first unchecked `[ ]`; smoke test gates pass/fail |
| Vish swap-in introduces bugs the smoke test doesn't catch | Low | After Vish merges, re-run T22 smoke test before any demo rehearsal |

---

## Research Notes

See `docs/specs/agentmes-research.md` for the full research digest. Key references:
- `research/judges-intel.md` — judge profiles + trigger scripts
- `research/blaxel-deep-dive.md` — Blaxel API surface
- `research/redis-memory-deep-dive.md` — Agent Memory Server interface
- `research/redis-context-deep-dive.md` — Context Surfaces / `ctxctl`
- `research/wordware-deep-dive.md` — Wordware as natural language compiler
- `research/codex-deep-dive.md` — Codex CLI + replay strategy
- Master spec doc: `Agent MES - Kanban UI.docx` (Vish's locked function signatures)
