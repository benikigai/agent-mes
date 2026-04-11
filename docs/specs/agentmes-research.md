# Research: AgentMES

**Date:** 2026-04-11
**Phase:** Discovery (gated IN — new external APIs, cross-cutting greenfield, high cost of wrong assumption)
**Author:** Claude (Opus 4.6) for Ben

This is a digest of the research that informs `agentmes.md`. It is NOT the spec — the spec is the approved plan; this is the evidence behind the plan.

---

## 1. TUI library: Rich vs Textual vs curses

| Library | Cost to learn | Visual ceiling | Hackathon fit |
|---|---|---|---|
| **Rich** ⭐ | Already installed (transitive of `context-surfaces`) | High — `Layout`, `Live`, `Panel`, `Table`, `Progress`, ANSI styling | **Best** — zero install, ships in 6h, mature `Live` rendering |
| Textual | Async TUI framework on top of Rich | Highest — full widget system, mouse, dev tools | Adds 60-90 min framework learning; overkill for our use |
| curses | Stdlib only | Brittle, no styling | Hostile for a 6h build |

**Decision: Rich.** The `Layout` primitive handles nested split rows/columns trivially; `Live` plus a callback-driven update loop gives us the kanban animation; `Panel` + `Table` gives us the receipts feed.

Reference: `~/code/blaxel-codex-redis-hackathon/.venv/lib/python3.14/site-packages/rich/` (installed via `context-surfaces` transitively).

---

## 2. Seven-column kanban layout in Rich (cards grow as they progress)

```python
from rich.layout import Layout

STAGES = ["plan", "design", "build", "test", "review", "document", "deploy"]

root = Layout(name="root")
root.split_column(
    Layout(name="header", size=3),
    Layout(name="board"),
)
root["board"].split_row(*[
    Layout(name=stage) for stage in STAGES
])
```

`Live(root, refresh_per_second=10)` drives the animation. Each pipeline event triggers `dashboard.on_event()`, which re-renders all 7 columns by grouping tasks by `current_stage` and calling `render_column()` for each. Cards naturally appear/disappear as they transition.

**Cards self-contain history.** Each card is a Rich `Panel` whose body is a `Group` of one rich Text line per StageEvent. As `task.events` grows, the rendered card grows. No separate receipts panel — the audit trail lives inside each card.

Reference: Rich docs on Layout https://rich.readthedocs.io/en/stable/layout.html

Terminal real estate: ~100 cols × 60 rows recommended (cards in DEPLOY column will be 14+ lines tall when both tickets finish). Default macOS Terminal supports this; resize to taller before demo.

---

## 3. Receipts / changelog model — embedded inside the card

Every stage transition emits a `StageEvent` appended to `task.events`. The card's render function reads from `task.events` and produces a multi-line Panel body. **The card IS the receipt.**

```python
class StageEvent(BaseModel):
    timestamp: datetime
    stage: StageEnum
    agent: str             # "Opus 4.6" / "Codex" / "Gemini" / "Blaxel" / "Redis"
    action: str            # short human-readable
    metadata: dict         # typed fields per stage
    artifacts: list[Artifact]  # files/memories/sandboxes produced

class Artifact(BaseModel):
    type: Literal["file", "memory", "sandbox", "pr", "email"]
    ref: str               # filepath, memory_id, sandbox_id, PR url, etc.
    summary: str

SYMBOLS = {"PASS": "✓", "FAIL": "✗", "KILLED": "✗", "DRIFT": "⚠", "WARN": "⚠", "RUN": "⏳"}
INTERNAL_META_KEYS = {"status", "ticket_id"}

def render_card(task: MESTask) -> Panel:
    lines: list[Text] = [
        Text(task.intent, style="bold white"),
        Text("─" * 30, style="dim"),
    ]
    # Group events by stage so we can render section headers
    by_stage: dict[StageEnum, list[StageEvent]] = {}
    for event in task.events:
        by_stage.setdefault(event.stage, []).append(event)

    for stage in StageEnum:  # iterate in declaration order
        if stage not in by_stage:
            continue
        lines.append(Text(f"━ {stage.value.upper()} ━", style="bold cyan"))
        for event in by_stage[stage]:
            symbol = SYMBOLS.get(event.metadata.get("status", "PASS"), "•")
            agent_short = event.agent.split()[0]
            lines.append(Text(f"{symbol} [{agent_short}] {event.action}"))
            for key, val in event.metadata.items():
                if key in INTERNAL_META_KEYS:
                    continue
                lines.append(Text(f"   {key}: {val}", style="dim"))
            for artifact in event.artifacts:
                lines.append(Text(f"   → {artifact.type}: {artifact.ref}", style="green"))

    title = f"{'⚙' if task.type == 'code' else '✉'} {task.id}"
    border = {"merged": "green", "running": "blue", "blocked": "yellow", "killed": "red"}[task.status]
    return Panel(Group(*lines), title=title, border_style=border)
```

**Card contents in DEPLOY column for TKT-001 (final state, ~30 lines):**

```
┌──[⚙ TKT-001]──────────────────┐
│ OAuth /v2 rate limit fix       │
│ ──────────────                 │
│ ━ PLAN ━                       │
│ ✓ [Opus] classified=code       │
│    ac_count: 3                 │
│    blast_radius: isolated      │
│ ━ DESIGN ━                     │
│ ✓ [Opus] sketched architecture │
│ ✓ [Codex] scaffolded files     │
│    files: middleware.py        │
│ ✓ [Gemini] reviewed sketch     │
│ ━ BUILD ━                      │
│ ✓ [Codex] wrote diff           │
│    +47 / -3                    │
│    files: auth/middleware.py   │
│ ━ TEST ━                       │
│ ✗ [Gemini] iter 1: FAIL        │
│    error: ImportError          │
│ ✗ [Blaxel] iter 2: KILLED      │
│    egress: evil.example.com    │
│    killed_in_ms: 23            │
│ ✓ [Gemini] iter 3: PASS        │
│    pytest: 5/5 green           │
│ ━ REVIEW ━                     │
│ ⚠ [Opus] memory drift          │
│    memory: /v1/login           │
│    ticket: /v2/oauth           │
│ ✓ [HUMAN] approved             │
│ ━ DOCUMENT ━                   │
│ ✓ [Redis] lesson written       │
│    → memory: mem_4471          │
│ ━ DEPLOY ━                     │
│ ✓ [GitHub] PR opened           │
│    → pr: github.com/.../12     │
│    → sandbox: standby          │
└────────────────────────────────┘
```

**The card IS the audit trail.** Vishal Dani can read the entire history off the screen. Adam Chan sees structured metadata fields, not free text.

Vishal Dani's enterprise audit-trail bias is satisfied — the entire history is visible on the final card. Adam Chan's "structural not heuristic" bias is satisfied — events are typed StageEvent objects with metadata fields, not free text.

A SIMPLE ticket finishes the pipeline with ~7 lines on its card. A CODE ticket finishes with ~14 lines because Test stage appends one line per loop iteration and Review appends separate lines for the drift catch and the human gate.

---

## 4. Two ticket types — same pipeline, type-aware stage prompts

| Stage | SIMPLE (knowledge work — email) | CODE (code change) |
|---|---|---|
| Plan | Extract recipients, subject, key points | Extract feature spec, blast radius, AC |
| Design | Fetch similar past emails (Redis Memory) | Hydrate ground truth (Context Surfaces) + past code lessons (Memory) |
| Build | Codex drafts the email body | Codex writes diff in worktree (replay) |
| Test | Gemini reviews tone, grammar, completeness | Gemini runs pytest in Blaxel sandbox; loop until pass |
| Review | Opus checks if email matches intent | Opus catches memory drift; HITL gate |
| Document | Write "sent email" lesson to Redis | Write decision log to Redis |
| Deploy | Save to `.demo/outputs/`, "would send via SMTP" | Open real GitHub PR with receipts as PR body |

**The classifier lives in `stages/plan.py`.** For the demo it can be a 3-line heuristic: if the intent contains code-shaped keywords (`fix`, `implement`, `refactor`, `bug`, etc.), classify CODE; else SIMPLE. Real deploy would use Opus for classification.

This is the architectural insight that makes AgentMES generalizable. **Same orchestrator + same 7 stages + type-aware stage prompts = one MES, two work types.** Demo runs both in parallel.

---

## 5. GitHub PR strategy at Deploy

Decision: **Hybrid (Option D)** — in-memory receipts during the pipeline, real GitHub PR opened only at the Deploy stage for CODE tickets. SIMPLE tickets save to a local file.

| Why not commit per stage? | Why not no commits at all? |
|---|---|
| Each `gh api` call is 1-3s. 7 stages × 2 tickets = 14 commits = ~30s of network during demo. Demo killer. | Vishal Dani asks "where's the audit trail?" and the answer is "in memory." Bad answer. |

The PR body includes the **full StageEvent receipts** as a Markdown table — that's the audit trail.

For SIMPLE tickets the Deploy stage writes:
- `.demo/outputs/email-{ticket_id}.md` — the drafted email
- `.demo/receipts/{ticket_id}.json` — the receipts list

Reference for PR body templating: `gh pr create --body-file <path>`.

---

## 6. Stub-first / interface-first pattern

Vish has function signatures locked in `Agent MES - Kanban UI.docx`. AgentMES MUST conform to those signatures verbatim so the swap from stub to real impl is a single import line change.

```python
# agent_mes/interfaces.py — the contract Vish builds against AND stubs satisfy
class RedisMemoryProtocol(Protocol):
    async def hydrate(self, query: str, session_id: str, limit: int = 3) -> list[dict]: ...
    async def cross_check(self, claim: str) -> dict: ...
    async def write_lesson(self, text: str, topics: list[str], user_id: str, negative_constraint: bool = False) -> str: ...
    async def seed_demo_memories(self, fixtures: list[dict]) -> None: ...

class ContextRetrieverProtocol(Protocol):
    async def query_entity(self, entity_type: str, entity_id: str) -> dict: ...
    async def list_related(self, entity_type: str, filter_dict: dict) -> list[dict]: ...
    async def verify_claim(self, claim: str, entity_type: str) -> dict: ...

class BlaxelVerifierProtocol(Protocol):
    async def create_sandbox(self, task_id: str, blast_radius: dict) -> "Sandbox": ...
    async def run_check(self, sandbox, machine_check: str) -> dict: ...
    async def self_heal_loop(self, sandbox, code_diff: str, checks: list[str], max_iterations: int = 3) -> dict: ...
    async def detect_egress_violation(self, sandbox) -> dict | None: ...
```

Stages take these via constructor injection. Default DI wiring = stubs. Real wiring = pass `RedisMemory()` from `vish/redis-blaxel` branch when it merges.

---

## 7. Choreographed stub design

Stubs are NOT random — they are deterministic and choreographed for the demo. Same beats every rehearsal:

| Stub call | Returns |
|---|---|
| `RedisMemory.hydrate(query="auth rate limit")` | 3 seeded memories incl. the adversary `"auth rate limiter fixed last month, conf 0.9"` |
| `RedisMemory.cross_check("auth rate limiter fixed")` | `{contradicted: True, contradicting: [{endpoint: "/v1/login", task_endpoint: "/v2/oauth"}]}` |
| `ContextRetriever.verify_claim(claim, "incident")` | `{verified: False, actual: {endpoint: "/v1/login"}, discrepancy: "endpoint mismatch /v1/login vs /v2/oauth"}` |
| `BlaxelVerifier.self_heal_loop(...)` | 3 iterations: iter1=fail-on-import, iter2=fail-on-egress-kill (returns the BLAST_RADIUS_VIOLATION log), iter3=pass |
| `BlaxelVerifier.detect_egress_violation(sandbox)` | On iter2: `{violated_at: now, destination: "evil.example.com", killed_in_ms: 23}` |

The demo runs the same sequence every time. When real APIs land, the choreography stays — only the data source changes.

---

## 8. Asciinema replay player options

Codex Build stage uses replay mode (`recordings/codex_build_run.cast`). Three options for replaying inside a Rich panel:

| Option | Approach |
|---|---|
| **A. Subprocess `asciinema play`** | Spawn `asciinema play --speed=8 recordings/codex_build_run.cast` in a subshell visible in a tmux pane. Doesn't fit inside Rich; needs external pane. |
| **B. Parse the .cast file** ⭐ | The `.cast` format is JSONL — `[timestamp, "o", "text"]`. Parse line-by-line, write to a Rich `Panel` with controlled timing. Lets us scrub speed and stop on demand. |
| **C. Pre-render to a Rich-friendly format** | Convert .cast → list of frames at build time, replay frames during demo. Most polished but most code. |

**Decision: B.** Parse the `.cast` JSONL inline, write to the BUILD column panel via `Live` updates. Ship the recording as a fixture in `recordings/codex_build_run.cast`. Speed control via a multiplier on the timestamp deltas.

For H7 we use a real Codex CLI call (one shot, max 30 min budget) to GENERATE the recording. If Codex is unreachable or slow, ship with a hand-crafted `.cast` file that simulates the same output sequence.

Reference: asciinema cast format https://docs.asciinema.org/manual/asciicast/v2/

---

## 9. Multi-model agent assignments per stage

Ben locked these in chat:

| Stage | Agents | Notes |
|---|---|---|
| Plan | Opus 4.6 | Single agent — classifies ticket type, extracts AC |
| Design | Opus 4.6 + Codex + Gemini reviewer | **Three sub-agents emit three StageEvents** — Opus sketches, Codex scaffolds, Gemini reviews |
| Build | Codex | Single agent — replay mode |
| Test | Gemini | Wrapped in Blaxel sandbox; iterates until pass or max_iterations |
| Review | Opus 4.6 | Drift catch; emits HUMAN gate event |
| Document | (no agent — data sink) | Calls `RedisMemory.write_lesson()` |
| Deploy | (no agent — data sink) | Calls `RedisMemory.write_lesson()` for monitoring breadcrumb + opens GitHub PR for code tickets |

For the MVP stub, "agents" are hardcoded labels recorded in StageEvent. No live LLM calls in the stub path. Real LLM calls are post-MVP additive tasks.

This gives **every major LLM provider** (Anthropic + OpenAI + Google) a role = strong "multi-model orchestration" judge angle for Dr. Max.

---

## 10. Risk register (rolled up to spec)

| Risk | Severity | Mitigation |
|---|---|---|
| Vish's signatures change mid-build | High | Stubs implement the locked signatures from the master doc verbatim. If Vish needs to change one, he announces in the shared thread first (master doc rule). |
| Demo terminal too small for 100×30 layout | Medium | Test on demo display during H8. Fall back to single-lane layout if needed. |
| Asciinema replay timing feels off | Medium | Speed multiplier configurable. Hand-craft the .cast file if real Codex run produces ugly output. |
| Live Codex call in H7 takes >30 min | Medium | Hard kill at 30; ship the hand-crafted .cast. |
| Multi-model demo angle reads as marketing | Low | StageEvents have real metadata fields per agent — receipts panel proves it's structured, not vibes |
| GitHub API rate limit during demo PR creation | Low | Use authenticated `gh` CLI; cap at 2 PRs per demo run (one for the code ticket only) |

---

## 11. References

- `research/judges-intel.md` — judge profiles and trigger scripts
- `research/blaxel-deep-dive.md` — Blaxel API surface (wraps Vish's blaxel.py)
- `research/redis-memory-deep-dive.md` — Agent Memory Server interface
- `research/redis-context-deep-dive.md` — Context Surfaces / `ctxctl` CLI
- `research/wordware-deep-dive.md` — Wordware as natural language compiler
- `research/codex-deep-dive.md` — Codex CLI + asciinema replay strategy
- `research/state-2026-04-11.md` — open questions, strategic decisions, judge intel summary
- Master spec doc: `Agent MES - Kanban UI.docx` (Google Doc 1YRLg0e0...) — Vish's locked function signatures
