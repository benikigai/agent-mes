# AgentMES — Redesign Proposal

**From demo choreography to a genuinely well-designed system, without losing the zero-token public demo**

**Repo:** `/Users/elias/code/agent-mes` (~6.4k LOC in `agent_mes/`, ~10k with web/tests/docs) · **Deployed:** https://agentmes.kogenlabs.dev · **Date:** 2026-06-13

---

## 1. Executive summary

AgentMES already has the right spine. The event-sourced receipt log (`task.events`), the Protocol + constructor-injection seam (`interfaces.py`), the live-streaming gate mechanism, and a production-quality real-PR flow are genuinely good engineering — not demo scaffolding. The problem is that three things drifted apart from those good bones:

1. **The pipeline is narratively, not causally, linked.** Build hardcodes `+47/-3` under a comment claiming it parsed them (`build.py:128-131`); Test verifies `"(stubbed diff)"` (`test.py:145`); Deploy commits a constant from `demo_patches.py`. The system's pitch is provenance, but there is no chain of custody.
2. **The signature concept — a bipartite human/agent state machine — has its weakest implementation.** Review rejection is a semantic no-op (`review.py:122` sets `status="running"` and the pipeline proceeds); web mode has no real reject endpoint; `task.status` is mutated across four files with no transition table.
3. **The public deployment is exposed today.** A live stored-XSS path from anonymous feedback → the operator's browser, an unauthenticated shared singleton board, an unbounded SSE amplifier, and visitor writes appended to a git-tracked file that auto-pushes to Ben's GitHub every 6h.

This proposal organizes the twelve adversarially-verified recommendations into **three architectural directions**, scores each against the Three Es, and recommends **Direction A — the Honest Simulation Engine**: one stage contract with three configurations (stub / replay / live), provenance stamped on every receipt, and a real transition table. Direction A is the only path that satisfies *both* halves of the stated goal simultaneously — a genuinely real Fable-5 system *and* a zero-token public demo — at the smallest safe diff. Directions B and C are correct in vision but over-scoped for a solo-maintained prototype now; their genuine wins are extracted and folded into A's later phases.

The Fable-strengths blueprint (Section 4) puts the expensive model exactly where the product thesis says judgment lives — `claude-fable-5` at the Review drift-catch gate — and Haiku 4.5 on the five throughput stages, for a real end-to-end ticket under **~$0.25**, while simulation mode stays the zero-token default.

---

## 2. Architecture today — the honest map

**One-line summary:** a deterministic, event-sourced demo choreography engine with genuinely excellent seams for becoming a real system, whose pipeline is narratively rather than causally linked, and whose three layers of truth (docs, tests, deployed config) have drifted apart.

### The good bones (preserve all of these)

| # | Asset | Why it's load-bearing |
|---|---|---|
| 1 | **Event-sourced receipts as single truth** (`task.events`) | Append-only audit log consumed identically by both renderers; the dual-renderer requirement falls out for free; refresh self-heals. The right spine — it just needs a provenance field per event. |
| 2 | **Protocol + constructor-injection seam** (`interfaces.py`) | Proven, not aspirational: the web path swapped in a plushpalace adapter + live Blaxel verifier without touching a single stage. Missing only typed payloads and one factory. |
| 3 | **Live-streaming gate** (`base.py` `_emit_event → _fire`) | The kanban updates *while* a human gate blocks, lock-serialized across parallel tasks. Correct design insight; the private `_pipeline._fire` handshake just deserves a declared interface. |
| 4 | **Domain vocabulary** | `BlastRadius` (allowed_paths/egress/cost), `AcceptanceCriterion.machine_check` (executable done-checks), `MemoryProvenance`, `HumanGate` — the correct primitives for agent manufacturing. Under-enforced, not wrong. |
| 5 | **Drift-catch loop** | Agent recall cross-checked against schema-typed ground truth, confidence demoted on contradiction, human gated on the discrepancy. Generalizes far beyond the demo. |
| 6 | **Graceful-degradation discipline** | `connect_or_none`, `build_plushpalace_adapter_or_none`, live→stub fallback with a visible WARN, exceptions→FAIL events. The public demo essentially cannot 500. |
| 7 | **`_open_real_pr`** (`deploy.py`) | Disposable worktree off `origin/main`, real `difflib` diff, `gh pr create --body-file`, guaranteed `finally` cleanup. The best code in the repo — it just deserves real provenance feeding it. |
| 8 | **Web concurrency primitives** | Order-independent `GateRegistry`, namespaced `task_id:stage` keys, per-launch pipeline instances, snapshot-on-connect SSE. |
| 9 | **Replay-as-architecture** (`CodexReplayBuilder`) | `AsyncIterator[str]` with timing-scaled `.cast` replay already embodies the winning zero-token pattern: record real once, replay free forever. Only the recorder is missing. |
| 10 | **Heliograph fixtures + narrative-lint tests** | Documented traps, realistic filler, a clean lookup API, and an executable choreography contract. The smoke test's *concept* (beats + latency budget as a demo-readiness gate) is exactly right. |

### The structural gaps (what the redesign fixes)

Every weakness traces to one of five missing structures:

1. **One composition root** — mode logic exists three times with three env polarities (`AGENTMES_BLAXEL_STUB=1` opts out, `AGENTMES_OPEN_REAL_PR=1` opts in, `AGENTMES_USE_PLUSHPALACE=0` opts out); `_pre_classify`/`_new_task` are copy-pasted verbatim between `cli.py` and `server.py`; **`/api/mode` reports `blaxel_live:true` while the deployed venv cannot import blaxel** (verified live — a `uv sync` stripped undeclared deps and nothing noticed).
2. **A real transition table** — `task.status` mutated across `pipeline.py`/`review.py`/`deploy.py`/`plan.py`; "what can happen next" is answerable nowhere; Review reject and Deploy reject have opposite semantics.
3. **Typed stage I/O** — `context_bundle: dict[str, Any]` is the inter-stage bus; Design wholesale-reassigns it and must hand-preserve keys; the dead `StageResult` enum sits unused while `metadata['status']` is the shadow enum.
4. **Provenance on `StageEvent`** — real receipts (live Blaxel URLs, real PR URLs) are structurally identical to fiction ("0 lint errors" from no linter; fabricate-first-claim drift).
5. **Replay as a first-class mode** — the `.cast` builder proves the pattern; promoting it to the semantic layer is the only thing that delivers real + zero-token at once.

**The public deployment is invisible in the repo** (zero tracked mentions of kogenlabs/cloudflared/LaunchAgents), the README is the most-wrong document in it, and 15/80 tests fail — all assertion rot, while the production wiring has zero coverage.

---

## 3. The redesign — three architectural directions

### Direction A — The Honest Simulation Engine *(RECOMMENDED)*

**Approach.** Keep the event-sourced spine and the Protocol seam exactly as-is. Make the *minimum* set of structural changes that turn the demo's biggest liabilities into features: (1) stamp every receipt with `provenance: live|replay|stub|narrative` so honesty becomes the product, not a risk; (2) make the bipartite machine real with a small transition table, a tristate `GateDecision`, and an actual reject; (3) collapse the three composition roots into one `factory.py` + `resolve_backends()` that *constructs* backends and reports what it actually built; (4) inject a `Pacer` so pacing leaves the domain layer; (5) revive the test suite green-on-real-wiring. Then promote replay to a first-class mode so the public demo replays recorded real runs. This is R1–R6 + R8(UI-only slice) — the subset every adversarial verdict converged on as "ship now."

**Strengths.** Smallest safe diff. Every change is additive or net-deletion (revive the dead `StageResult`, delete two duplicated `GateProvider` aliases and two `_await_human` copies, retire three mode-logic copies). The zero-token demo is *strengthened* — defaults stay stub, the public topbar chip stops lying. It is the direct prerequisite for the Fable-strengths blueprint (provenance + transition table + one factory are what live mode plugs into) without committing to the larger rewrites yet.

**Weaknesses.** Does not, by itself, make Build's output flow to Test and Deploy (the value chain stays narrative until Direction B's typed I/O lands — though the +47/-3 lie gets fixed cheaply). Provenance defaults to `narrative` on most events, which is honest but means the badges mostly say "scripted" until live mode arrives.

**Tradeoffs.** You give up the satisfying clean-room rewrite in exchange for a system that is shippable in independent slices, never has a broken intermediate state, and keeps the demo live throughout. You gain the honesty field that is the *prerequisite* for live mode not lying — which is the single highest-leverage change in the codebase.

| Three Es | Score | Justification |
|---|---|---|
| **Elegant** | 9/10 | Five named structures replace a dozen emergent ones; the transition table makes the bipartite thesis inspectable instead of folklore; provenance converts the credibility liability into the product's honesty feature. −1: provenance-defaults-to-narrative is a transitional half-truth until live lands. |
| **Efficient** | 9/10 | Almost entirely S/M, much of it net-deletion. No new abstraction with one consumer (`resolve_backends` has 3+: `_build_pipeline`, `/api/mode`, `/healthz`, boot line). Lowest token/runtime/cognitive cost of the three. |
| **Effective** | 9/10 | Solves the two real problems Ben named (genuinely-designed + zero-token) and closes the live security exposure today. Low regression risk because the demo stays live in every slice. −1: value-chain causality deferred to a later phase. |

### Direction B — The Typed Value-Chain Rebuild

**Approach.** Everything in A, plus the deeper structural move: introduce `io_types.py` with typed per-stage Output models (`PlanOutput → … → DeployInput`), replace `context_bundle` entirely, put a per-stage `Engine` Protocol (stub/replay/live) behind each stage, and make the value chain *causal* — Build's real diff flows to Test's sandbox and Deploy's PR, deleting `demo_patches.py`. This is R7 layered on A.

**Strengths.** Fixes the deepest gap: the receipts chain finally has a chain of custody. Unlocks the cheapest realness win in principle — Test executing real `machine_check` commands against a real diff. Typed Protocol payloads turn stub/adapter drift into a validation error instead of a rendering surprise.

**Weaknesses.** Verification refuted the flagship payoff as currently scoped: the TKT-001 acceptance criteria (`pytest tests/auth/test_oauth_token_refresh.py --count=100`) point at a test suite that **does not exist in the repo**, and `FIXED_OAUTH_MIDDLEWARE` is a standalone string with no runnable harness — so "execute the real checks at zero tokens" errors on missing files, not green verdicts, until someone authors the suite + fixtures. Worse, the headline wow-moment (the choreographed egress-kill on iteration 2) *cannot* be reproduced by a real pytest run, so stub and live necessarily diverge exactly where B claims they'd unify. Replacing `context_bundle` touches `schema.py` + all 7 stages + `interfaces.py` + ~36 call sites + the 1,327-line `artifacts.py` that renders the visible demo output — multi-day, high regression risk on the public surface.

**Tradeoffs.** You gain true provenance end-to-end; you pay L-effort and accept regression risk on the demo's most visible artifact, for a payoff whose flagship piece needs net-new test authoring B doesn't budget. The ~30-line truth-fix (compute the real diff once, thread it Build→Test→Deploy) captures the honest core without the rewrite.

| Three Es | Score | Justification |
|---|---|---|
| **Elegant** | 8/10 | Typed I/O + one Engine Protocol per stage is the *correct* long-term shape — stub/replay/live become three configs of one machine. −2: every Engine has exactly one implementation today, so the abstraction is ahead of its consumers. |
| **Efficient** | 4/10 | L-effort rewrite touching the entire stage surface + artifacts + 21 test files; the flagship "zero-token real checks" requires unbudgeted suite authoring. High diff, deferred payoff. |
| **Effective** | 6/10 | Fixes the real causality gap, but endangers the 10-second wow (egress-kill can't go live) and the visible receipts during the migration window. Effective *eventually*, premature *now*. |

### Direction C — The Multi-Tenant Product Platform

**Approach.** Everything in A, plus turn the demo into a product: per-visitor `DemoSession` boards (R10) so every visitor drives their own pipeline, a sequenced event-log wire protocol with `run_id`/`seq` and Redis-backed replay (R11), and a guarded `/api/intake` with ticket playbooks as type-as-data (R12) so anyone can paste a ticket and watch it flow.

**Strengths.** "Paste your own ticket and watch it flow" is the moment the project stops being a movie and becomes a product — the highest demo-value-per-line idea available. Per-session boards are the right experience for "try the human gate yourself." The wire protocol is the foundation a real fleet view would stand on.

**Weaknesses.** Almost every piece is an abstraction with effectively one consumer today, justified by hypothetical futures (fleet view, replay feed) that don't exist. The `SessionRegistry` + janitor + LRU adds its own concurrency lifecycle bugs; per-session artifacts require threading a session root through `pipeline.run` → 7 stages → `artifacts.py` → `OUTPUTS_DIR` and making read routes session-scoped (the sketch's "routes unchanged" is false — every session reuses the same `TKT-001` ids, so `{sid}` *must* enter the read path) → L, not M. The wire-protocol rewrite fixes O(n²) at n≈30 events behind cloudflared — scaling a problem the demo will never hit — and rewrites the live render path, endangering the wow moment for no visible gain. The intake feature, post-honesty-fix, produces an *honest but boring* flow (no drift catch, no `+47/-3`) — it extends honesty, not wow.

**Tradeoffs.** You gain a genuine product surface; you pay L-effort building multi-tenant machinery and a build-step contract generator for a solo public prototype, with several pieces refuted as premature. The cheap 80%: adopt R1's operator-token as the *product* fix (presenter mutates, visitors watch read-only) — kills every multi-visitor failure mode with zero sessions/cookies/janitor.

| Three Es | Score | Justification |
|---|---|---|
| **Elegant** | 6/10 | The data model is right and forward-compatible, but it's architecture for a future that may not arrive; several abstractions (SessionRegistry, wire-protocol run-log, contract generator) have one consumer. |
| **Efficient** | 3/10 | Multiple L-effort builds, each hand-waving real work (task-id-keyed artifact rewrite, build-step in a deliberately build-free frontend). Highest cost of the three. |
| **Effective** | 6/10 | The intake feature is genuinely high-value, but the platform machinery around it is premature and the wire rewrite endangers the demo. The 5%-effort operator-token version captures ~80% of the correctness value. |

### Recommendation: Direction A

**Direction A wins decisively on Efficiency and ties on Elegance/Effectiveness.** It is the only direction that:

- closes the *live* security exposure on agentmes.kogenlabs.dev today (B and C bury it under a rewrite),
- ships in independent slices that never leave the demo broken,
- strengthens rather than risks the zero-token default and the 10-second wow,
- and lays exactly the foundation (provenance field + transition table + one factory + typed-output-ready seam) that the Fable-strengths blueprint plugs into.

B and C are not wrong — they are *later*. Their genuine wins are extracted into A's roadmap: B's ~30-line diff-truthing fix lands in Phase 1; B's full typed I/O and C's intake endpoint become Phase 2/3 *once a real second consumer exists* (a live engine; a third ticket type). The rule Ben set — never present a bare choice without analysis, design for graceful degradation and no rework when requirements evolve — is exactly why A is right: it is the diff that doesn't have to be re-done when live mode and multi-tenancy arrive.

---

## 4. Fable-strengths blueprint — the design for real-agent mode

The hardest part of going live was done at hackathon hour zero: `MESTask`'s planning fields *are* the shape a structured-outputs parse returns (`plan.py` already does `AcceptanceCriterion(**ac)` / `BlastRadius(**...)` from a dict), and 5 of 7 stages are single-call extraction/judgment tasks, not agents. Real mode lives behind a `[live]` extra and `AGENTMES_LIVE=1`; **the public default stays stub/replay (zero tokens, guaranteed).**

### Model-per-stage (judgment-where-it-belongs)

| Stage | Model | Call shape | Why |
|---|---|---|---|
| **Plan** | `claude-haiku-4-5` | `messages.parse(output_format=PlanOutput)` | Pure extraction into the existing schema. Deletes both keyword classifiers + the Wordware fixture path. |
| **Design** | `claude-haiku-4-5` | `messages.parse(output_format=DesignOutput)` | Hydrate memories + ground-truth entities → approach. Throughput. |
| **Build (phase 1)** | `claude-haiku-4-5` / `claude-sonnet-4-6` | one `messages.parse(output_format=BuildOutput{diff})` against `demo-runs/code-template` | Replaces `demo_patches.FIXED_OAUTH_MIDDLEWARE` with model output; one call, no agentic loop. |
| **Test** | **none — zero tokens** | execute `machine_check` in the Blaxel microVM; Haiku summarizes stderr *only on failure* | The cheapest realness lever: real verdicts at zero tokens against the already-real sandbox. |
| **Review** | **`claude-fable-5`**, `thinking:{type:"adaptive"}`, `effort:"high"` | `messages.parse(output_format=ReviewOutput)` over memory provenance + shortlisted records + the diff | **The expensive frontier model goes exactly where the product thesis says judgment lives.** Makes the gold drift-catch moment a *real* Fable-5 verification. |
| **Document** | `claude-haiku-4-5` | `messages.parse(output_format=DocumentOutput)` | Lesson + topics extraction. Throughput. |
| **Deploy** | **none — gh + worktree** | the existing production-quality `_open_real_pr`, now fed the real `BuildOutput.diff` | Already the best code in the repo; just give it real provenance. |

> Per the API reference: Fable 5 requires `thinking:{type:"adaptive"}` (a `budget_tokens` or explicit `disabled` returns 400 — omit `thinking` to disable); structured outputs use the canonical `output_config:{format:{...}}` (or `messages.parse`). Replace the rotting hardcoded `"Opus 4.6"`/`"Codex"`/`"Gemini"` agent strings with a `Role` enum + `MODEL_FOR_ROLE` registry so a model bump is one line.

### Agent SDK shape

- **5 of 7 stages are single `messages.parse` calls**, not agents — keep them that way. Do not reach for Managed Agents where a structured extraction call suffices (the API guidance is explicit: start at the simplest tier).
- **Build phase 2 (deferred, Phase 3):** a manual tool-use loop (`read_file`/`edit_file`/`run_check`) over a disposable worktree cloned from `deploy.py`'s existing machinery, with `BlastRadius.allowed_paths` enforced in the tool handlers — a real `is_error` on violation becomes the *real* egress-kill moment. Managed Agents + `define_outcome` (each `machine_check` = one gradeable rubric criterion) is the natural upgrade path. Scoped as a separate L follow-up, not folded into the M core, because making the egress-kill real requires authoring a runnable test suite the demo currently lacks.

### Structured-output contracts

`io_types.py` (introduced incrementally — only the slots that gain a real second implementation):
`PlanOutput{intent, ticket_type, acceptance_criteria, blast_radius}` · `DesignOutput{memories, ground_truth, approach}` · `BuildOutput{diff, files_changed, stats, email_body?}` · `TestOutput{check_results[{criterion, passed, stdout, stderr}], sandbox_ref}` · `ReviewOutput{verdict: approve|drift|reject, drift_findings[{claim, record_id, explanation}]}` · `DocumentOutput{lesson, topics}`. These double as the Protocol payloads, so stub/adapter shape drift becomes a Pydantic validation error.

### Prompt-caching strategy

One **stable system prefix** = MES role prompt + plushpalace corpus block, shared **byte-identical** across Plan/Design/Review and placed above the 4096-token minimum cacheable prefix for Opus/Haiku (Fable 5's minimum is 2048). Render order `tools → system → messages`; the per-ticket `raw_input` / claim goes *after* the last `cache_control` breakpoint. Verify with `usage.cache_read_input_tokens` in the ledger — if it's zero across tickets, a silent invalidator (a `datetime.now()` in the prefix, unsorted JSON) is at work. No `datetime`, no UUID, no per-ticket string in the cached prefix.

### Cost envelope per real ticket (`AGENTMES_LIVE=1`)

Rough order-of-magnitude for one CODE ticket, corpus cached after the first stage:

| Stage | Model | ~Input (cached/uncached) | ~Output | ~Cost |
|---|---|---|---|---|
| Plan | Haiku 4.5 | 6K cached + 1K | 0.5K | ~$0.005 |
| Design | Haiku 4.5 | 6K cached + 2K | 1K | ~$0.008 |
| Build p1 | Haiku 4.5 | 3K | 2K | ~$0.013 |
| Test | — (sandbox) | — | — | $0.00 |
| **Review** | **Fable 5** | 6K cached + 4K | 2K (incl. thinking) | **~$0.14** |
| Document | Haiku 4.5 | 6K cached + 1K | 0.5K | ~$0.005 |
| Deploy | — (gh) | — | — | $0.00 |
| **Total** | | | | **~$0.17–0.25** |

The Fable-5 Review call dominates — which is correct: judgment is where the spend belongs. **Wire the dead `BlastRadius.max_cost_usd` into a real kill-switch:** the live engine accumulates `usage × price` per stage; `BudgetExceeded → existing FAIL path → status="killed"`. Today `max_cost_usd` is read by zero enforcement lines (only `artifacts.py`/`fake_slack.py` display/seed it) — this finally activates a dead blast-radius dimension. (Skip the Batches API 50%-discount optimization for ~6 one-time per-ticket requests — it saves cents, adds polling complexity, and doesn't fit the multi-turn Build loop. Use plain streaming.)

### How simulation stays the zero-token default

- **Public default is `replay` (or `stub`)** — `AGENTMES_LIVE` unset. No `anthropic` import on the public hot path (it lives behind the `[live]` extra).
- **The interlock** (`AGENTMES_PUBLIC=1` in the deployed plist) forces stub backends + `dry_run=True` + `seed_plushpalace(flush=False)` regardless of other flags.
- **Golden-run record/replay** (the existing `.cast` builder generalized): `agent-mes record --ticket TKT-001` runs the live engine *once*, writes `recordings/transcripts/{ticket}/{stage}.json` with the real `Exchange{model, usage, request_id, output}`, commits it. Public visitors replay the recorded run deterministically — **public receipts trace to real Fable-5 exchanges with real request IDs**, while the room sees zero tokens spent. Replay even demos the human gate (it pauses on a blocked gate so the real APPROVE button resumes the feed) — something a video cannot do.

---

## 5. Hardening the public demo

All four exposures verified live against the deployed code; nothing in the repo mitigates them today.

| Item | Fix | Effort |
|---|---|---|
| **Stored XSS** (the one input→code-exec path) | Anonymous `POST /api/feedback` text → `context_bundle['operator_feedback']` → rendered verbatim by `render_plan` (`artifacts.py:264` `> {fb}`) → served through `marked.parse → innerHTML` at `/output` (`server.py:657`) and `/artifact` (`:692`), where marked@12 does not escape HTML. **Wrap both sinks in `DOMPurify.sanitize(marked.parse(...))`; vendor marked+DOMPurify locally with SRI hashes.** (~20 min — the real fix; source-side `html.escape` is secondary.) | S |
| **Visitor writes auto-pushed to Ben's GitHub** | `StubRedisMemory.write_lesson` appends to git-tracked `.demo/memory_log.jsonl` every run (the live box falls back to the stub — plushpalace isn't importable), and `workspace-git-sync` pushes it under Ben's identity every 6h. **`git rm --cached .demo/memory_log.jsonl .demo/outputs/*.md`, add to `.gitignore`, point the log at an untracked tmp dir.** (~10 min — highest signal-to-effort.) | S |
| **Unbounded SSE amplifier** | `EventBroker._subscribers` is an unbounded list of unbounded `asyncio.Queue()`; `publish` is O(events × subscribers) on a single uvicorn worker; the generator is `while True`. **`Queue(maxsize=64)` with drop-slow-subscriber-on-overflow, `MAX_SUBSCRIBERS ≈ 50` (503 past it), idle cap on the generator.** | S |
| **Front-door rate limit** | Cloudflare rule: rate-limit `POST /api/*` (~10/min). No code, doesn't block watching or the wow-run. | S |
| **Decide: playground vs console, then control mutations** | The fork the proposal must resolve: full token-gating of `/api/launch` turns a public showcase ("anyone clicks Start and watches") into an operator-only console — a real product downgrade. **Recommended:** keep launch public; de-grief the shared board by requiring an operator token on the *destructive* mutations (`/api/reset`, `/api/approve`, `/api/feedback`) only, so a visitor can't reset someone else's demo or approve their gate. Simplest path if you want a true console instead: a Cloudflare Access email allowlist over the whole site (no bespoke token + app.js chip). | S–M |
| **Crash forensics** (fold in from R4) | `pipeline.py:58` truncates errors to `str(exc)[:50]`, no traceback logged anywhere; the failure path fires the events callback *before* `status="killed"`, and `server._run`'s `try/finally` has no `except` — a raising callback freezes the card. **Add stdlib `logging`, `logger.exception` on the failure path, reorder status-before-fire, guard the failure `_fire`, add `except+log` to `_run`.** | S |
| **Note (already safe)** | The deployed plist already binds `127.0.0.1` (exposure is the tunnel, not the bind) and `AGENTMES_OPEN_REAL_PR=0` already dry-runs PRs — so the bind-flip and PR interlock are insurance, not load-bearing. Don't oversell them. | — |

---

## 6. Phased roadmap

Each phase is independently shippable, keeps the demo live, and never spends a public token.

### Phase 1 — Highest leverage, smallest diff *(the "ship this week" set)*

The security-critical items plus the structural changes every verdict said ship-now. All S/M; net-deletion in several places.

1. **R1 (S):** the four guardrails above — DOMPurify both sinks + SRI, stop the git writes, SSE caps, Cloudflare rate-limit.
2. **R2 (M):** make the bipartite machine real — revive `StageResult` + add `REJECTED`, a ~10-line `TRANSITIONS` dict (one consumer, but the inspectable signature artifact), tristate `GateDecision{APPROVED, REJECTED, TIMED_OUT}` (timeout renders "expired"), `POST /api/reject`, `HumanGateProtocol` in `interfaces.py` replacing both `GateProvider` aliases and both `_await_human` copies, `launch_one` rebuilding via `_new_task + gates.reset_task` (making the `gates.py:44` docstring true). *Drop from the original sketch:* `kind:tool`/`ToolCallRef` (no consumer), `run_id` in approve bodies (echo `{stage}` + 409 on mismatch is enough), session-derived approver (one-line configured label). Replan stays server-owned (reuse the existing `/api/feedback` machinery).
3. **R3 (S — trimmed):** `StageEvent.provenance: Literal[...] = "narrative"` (additive, no migration); ~4 live/replay call-site clusters stamped; renderer badges in `app.js` + terminal; move `POSTMORTEM_TEMPLATE` to `demo/` fixtures (kills the `artifacts.py:717` import cycle); dedupe the Codex-vs-Opus contradiction (`artifacts.py:211` vs `:268`) and the 6×-duplicated `+47/-3` to one constant; add the missing render-all-stages-×-both-tickets test. *Defer:* `ExchangeRef` + `/transcript` viewer (no producer in stub mode) and the full `artifacts.py` collapse (163 f-string interpolations make it 600–800 lines, not <300 — M-L with regression risk on the visible receipts).
4. **R4 (M):** `factory.py` + `RunConfig` + `resolve_backends()` that *constructs* backends and reports `provenance`/`degraded`; `/api/mode` returns it verbatim; `GET /healthz`; one-line boot `BACKENDS ...` print; `[live]` extras in `pyproject.toml` so `uv sync` can never silently strip deps again; `test_mode_matches_wiring` (would have caught the live divergence). *Trim:* one `AGENTMES_CONTEXT` var for the memory+context pair (one adapter serves both) + `AGENTMES_VERIFIER` + keep `AGENTMES_OPEN_REAL_PR`; no env switch for single-impl seams (Planner, Builder).
5. **R5 (S):** `pacing.py` `Pacer` (profiles `demo 0.65` / `off 0`); rewrite the 44 linear stage sleeps to `await self.pace.beat(weight=...)`; handle the 2 `_await_human` sleeps explicitly; inject as a default kwarg at the 4 construction sites; `conftest.py` sets `Pacer(0)` + centralizes the 4 import-time `AGENTMES_AUTO_APPROVE` mutations. *Don't* build the combined `StageRuntime(emit,pace)` yet (needs the not-yet-built factory; the `_fire` handshake is independently justified).
6. **R6 (M — split):** `conftest.py` with autouse fixtures (`monkeypatch.setattr` the three module-level path constants — they are *not* env-driven; setting env vars does nothing), golden-subsequence invariants in `tests/helpers.py` (replace `len(events)==N` pins), one true `tests/test_web_e2e.py` (ASGITransport: launch → consume SSE to blocked-at-review → approve → blocked-at-deploy → approve → merged; assert a DRIFT event + two approval receipts), plus siblings for relaunch-no-autopass and reset-broadcast. *Wiring-drift check points at `/api/mode`'s real dict (`get_mode`), not the fictional `resolve_backends` the sketch names — extract its dict-builder to a pure helper first.* Defer the CI workflow and the README/runbook rewrite to Phase 2 (independent; don't bundle docs into the test-rot fix).
7. **R7 micro-fix (S):** the ~30-line diff-truthing — `compute_demo_diff()` helper computes the real unified diff once; Build derives `lines_added`/`removed`/`files` from it (deleting the `build.py:129-131` constants) and stashes it on `context_bundle['code_diff']`; Test reads it instead of `"(stubbed diff)"`; Deploy reuses the same helper. Makes Build→Test→Deploy causally consistent on the one fact that's currently faked, at zero demo risk.

**Phase 1 leaves:** a secure public demo, a real and inspectable bipartite machine, honesty badges on every receipt, one truthful composition root, a fast green test suite gating the real wiring, and the one load-bearing lie (the diff) made true.

### Phase 2 — The Fable-strengths core *(make it genuinely real, behind a flag)*

8. **R9 core (M):** `engines/live.py` behind the `[live]` extra + `AGENTMES_LIVE=1`; **public default stays stub/replay.** Plan + Design + Review as `messages.parse` structured-output calls (Haiku throughput, `claude-fable-5` at Review) with the shared cached corpus prefix; the real cost ledger wired to `max_cost_usd` as a kill-switch; the `Role` enum + `MODEL_FOR_ROLE` registry. *Defer Build phase-1 diff re-plumbing and the agentic loop.*
9. **R8 step 1 — UI replay (S, no SDK):** `agent-mes record --out recordings/canonical-run.events.jsonl` dumps the existing timed SSE stream; a ~40-line `ReplayFeed` in `app.js` exposes the EventSource interface and pauses on blocked gates; retire `replay.html` + `STAGE_MARKERS` + the third copy of the stage narrative. Kills the divergent asciinema page immediately, demos the human gate, touches zero LLM plumbing.
10. **R8 step 2 — semantic replay (M, after R9):** the live `Exchange` recorder + `ReplayEngine.run()` keyed by stage + canonical-input hash, stamping `provenance='replay'`; prove it on the Review seam first (highest-value real judgment, retires the string-match drift fiction) before generalizing.
11. **Docs (S):** rewrite README around the system as deployed; check in `deploy/` runbook (plists, cloudflared config minus credentials, restart procedure); banner `docs/specs/*` as historical; `.github/workflows/ci.yml` with the wiring-drift job asserting all-stub by default (proving the zero-token path stays zero-token).

### Phase 3 — Product surface *(only when a second consumer exists)*

12. **R12 honesty prereqs + thin intake (S→M):** make `wordware.py`'s fallback return a generic minimal plan synthesized from `raw_text` (not TKT-001's payload); fence `build.py`'s `+47/-3` and the postmortem template behind `task.id in FAKE_SLACK`; collapse the three classifier copies into one `classify()` function (delete the duplicated `_pre_classify`/`_SIMPLE_HINTS` and dead `_branch_by_type`) *without* the Playbook framework; add `POST /api/intake` guarded by `AGENTMES_INTAKE_TOKEN`. Defer the `Playbook`/`StageSpec`/`GateSpec` registry until a genuine third ticket type exists.
13. **R7 full (L):** typed `StageOutputs` replacing `context_bundle` + the per-stage `Engine` Protocol — only once a live engine is a real second implementation, and budget the missing acceptance-criteria test suite as part of it.
14. **R10 product fix (S, not the platform):** operator-token on destructive mutations = the multi-tenant correctness fix without `SessionRegistry`. Build the full per-session boards only with evidence visitors want to drive their own board, and price it L (the task-id-keyed artifact rewrite is the real work).
15. **R11 dead-link fix now (S), wire rewrite never-until-needed:** relax `isArtifactLink` to `startsWith('/')||startsWith('http')` — a one-line fix for the `/redis` and `/output` deep-links that currently render as dead text on both demo tickets. Defer the entire sequenced wire protocol / `run_id` / Redis ring buffer until a real replay/fleet feature creates a second consumer.

---

## 7. Explicitly rejected *(so they don't come back)*

| Idea | Why rejected | The salvaged sub-win |
|---|---|---|
| **Full typed `StageOutputs` rewrite now (R7 as L)** | Touches all 7 stages + `interfaces.py` + ~36 call sites + the 1,327-line `artifacts.py` rendering the visible demo + 21 test files; every Engine has exactly one implementation today (abstraction ahead of consumers); the flagship "Test runs real checks at zero tokens" *errors on missing files* — the TKT-001 test suite doesn't exist — and the headline egress-kill **cannot** be reproduced live, so stub/live diverge where it claimed they'd unify. | The ~30-line `compute_demo_diff()` truth-fix (Phase 1, item 7). |
| **`ExchangeRef` + `GET /transcript` viewer now (R3 tail)** | Zero producers in stub mode — no LLM exchange ever occurs in the public demo, so the endpoint ships dead. | Add the optional field only when the first live engine emits usage/transcripts (Phase 2). |
| **Per-session `SessionRegistry` + janitor + LRU (R10 as M)** | One real consumer; future-fleet justification explicitly deferred; "routes unchanged" is false (every session reuses `TKT-001` ids, so `{sid}` must enter read paths); adds its own concurrency lifecycle bugs; the only concurrency-dangerous stage (real PR) is already isolated by a disposable worktree. Honestly L, not M. | Operator-token on destructive mutations = the correctness fix at ~5% effort (Phase 3, item 14). |
| **Sequenced event-log wire-protocol rewrite (R11 core)** | Fixes O(n²) at n≈30 events behind cloudflared — scaling a problem the demo will never hit; rewrites the live render path (endangering the wow moment) for no visible gain; the "R8 replay foundation" it's justified by doesn't exist yet; adds a build step to a deliberately build-free frontend. | The one-line `isArtifactLink` dead-link fix (Phase 3, item 15). |
| **Playbook type-as-data framework (R12 core)** | A registry built to hold exactly two entries that already exist as two `if` branches; `GateSpec` couples to an unbuilt transition table (inner-platform risk relocated from YAML to dataclasses); `MESTask.type→playbook:str` ripples through ~30 `task.type.value` sites + the test suite. Honestly L, not M. | The honesty prereqs + one-function `classify()` + thin guarded intake (Phase 3, item 12). |
| **YAML pipeline configuration** | The inner-platform trap — a config language for a state machine that doesn't need one. Explicitly refuted in R12's own rationale. | None — the transition table is a ~10-line Python dict (Phase 1, item 2). |
| **Real Slack/GitHub webhooks for intake** | A stored-XSS factory until R1/R10 land; the moment intake becomes real, the unsanitized markdown sink is reachable by anyone. | Future webhooks become thin adapters posting into the same guarded `/api/intake` — nothing lost by deferring. |
| **Batches API for the 50% discount in live mode** | Premature optimization on ~6 one-time per-ticket requests (saves cents), adds batch-polling complexity, and doesn't fit the multi-turn Build loop. | Plain streaming (Section 4). |
| **`StageRuntime(emit, pace)` combined runtime now (R5 tail)** | Requires the not-yet-built factory; the `_pipeline._fire` event handshake is independently justified and shouldn't ride the pacing change. | Inject the `Pacer` alone as a default kwarg (Phase 1, item 5). |
| **Full token-gated operator-only console as the default** | Turns a public showcase where "anyone clicks Start and watches the pipeline run" into an operator-only console — a real product downgrade for a demo whose whole point is the live run. | Gate only the *destructive* mutations; keep launch public (Section 5). |