# Spec: AgentMES Web UI

**Date:** 2026-04-11
**Status:** Approved
**Approved option:** Option A — Modular FastAPI + vanilla JS
**Complexity:** Moderate (10 tasks: 8 Simple, 2 Moderate, 0 Complex)
**Branch:** `feat/agentmes-web` (off `main` at `b47a357`)
**Builds on:** `docs/specs/agentmes.md` (terminal MVP, complete, 60/60 tests)

---

## Context

The terminal MVP at `docs/specs/agentmes.md` ships a complete AgentMES pipeline: 7 stages, 5 sponsor integrations, choreographed stubs, demo fixtures (TKT-001 flaky test fix + TKT-002 postmortem). 60 tests pass. Pipeline code is **renderer-agnostic** — every stage emits `StageEvent` objects via a pluggable `events_callback` that the terminal `Dashboard` already consumes.

This extension adds a **second renderer** — a real interactive web kanban UI — that subscribes to the same `events_callback`. The pipeline, stages, stubs, integrations, demo fixtures, and schema all stay untouched. **Only ReviewStage** gets a backward-compatible optional parameter so the human gate can be satisfied via a browser button click instead of `input()`.

The terminal version remains as a fallback. Both renderers ship in the same repo on `main` after this branch merges.

## Decisions

### D1 — Pipeline reuse, zero refactoring
The web layer is purely additive. `agent_mes/{schema,interfaces,pipeline,stages/*,integrations/*,demo/*}.py` are unchanged. The web server constructs the existing `Pipeline` with the existing stage classes and the existing stub backends.

### D2 — `agent_mes/web/` package, three modules
- `events.py` — `EventBroker` with per-client `asyncio.Queue` subscribers
- `gates.py` — `GateRegistry` with per-task `asyncio.Event` registry for browser approvals
- `server.py` — FastAPI app with `/api/{state,launch,approve,events}` + static mount

Cleanest separation. Each module is independently testable.

### D3 — `ReviewStage` gets an optional `gate_provider` parameter
Backward-compatible single-line constructor extension:
```python
def __init__(self, redis, context, gate_provider=None):
    ...
    self.gate_provider = gate_provider

async def _await_human(self, gate):
    if self.gate_provider is not None:
        return await self.gate_provider(gate)
    # ... existing input() path unchanged
```
Default behavior unchanged. All existing 60 tests pass without modification.

### D4 — Vanilla HTML/CSS/JS frontend, no build step
- `web/index.html` — 7-column kanban + launch button + state header
- `web/style.css` — dark theme matching the existing asciinema page
- `web/app.js` — `EventSource` consumer + DOM updates + approve handlers
- ~250 LOC frontend total. No React, no Vite, no npm install.

### D5 — Server lifecycle: re-launchable
Each `POST /api/launch` resets the GateRegistry, builds fresh `MESTask` instances, builds fresh stub backends (so `StubBlaxelVerifier.iteration` resets), and runs the pipeline. Re-runnable back-to-back during pitch rehearsals without restarting the server.

### D6 — Bind 0.0.0.0:8000, viewable from MBP via Tailscale
`uvicorn agent_mes.web.server:app --host 0.0.0.0 --port 8000`. Reachable at `http://100.85.105.99:8000` from the MBP over Tailscale. macOS may prompt for incoming connection allowance on first launch — one click.

### D7 — Asciinema fallback at `/replay`
The existing `web/index.html` (asciinema-only player) moves to `web/replay.html`. Live kanban becomes the new `/`. Asciinema is the disaster-recovery URL.

### D8 — Inline `[APPROVE]` buttons (not modals)
When ReviewStage's HumanGate fires, the card shows an inline button. Ben clicks it on stage. Visible click = visible HITL beat.

### D9 — Refresh-safe SSE via push-state-on-connect
On `/api/events` connect, broker pushes the FULL current state of all tasks before subscribing to live events. Browser refresh mid-pipeline is self-healing.

---

## Three Es Options Analysis

### Option A — Modular FastAPI + vanilla JS ⭐

**Approach:** `agent_mes/web/{server,events,gates}.py` (3 modules) + `web/{index.html,app.js,style.css}` (3 files) + `web/replay.html` (asciinema). FastAPI for routing, sse-starlette for SSE, vanilla JS for the frontend.

| Criterion | Score | Reasoning |
|---|---|---|
| Elegant | 5 | Clean broker/gates/server separation; pipeline untouched |
| Efficient | 4 | 10 small tasks, ~2h total |
| Effective | 5 | Demo-grade reliability, real interactive UI, terminal stays as fallback |

**Architecture impact:** New `agent_mes/web/` package + new `web/` static assets. ReviewStage gets one optional parameter.
**Code churn:** ~10 files, ~600 LOC across backend + frontend + tests
**Failure modes:**
- SSE drop → browser auto-reconnects, broker pushes full state on reconnect
- Race on approve before gate → GateRegistry is order-independent
- Browser refresh → `/api/state` rehydrates
**Maintenance cost:** N/A — hackathon throwaway, but the renderer separation is genuinely production-grade.

### Option B — Single-file starlette + inline HTML

**Approach:** One `agent_mes/web.py` with starlette ASGI app and inline HTML/CSS/JS in Python f-strings. Skips fastapi install.

| Criterion | Score | Reasoning |
|---|---|---|
| Elegant | 2 | Inline HTML in Python is hostile |
| Efficient | 4 | 4-5 tasks |
| Effective | 3 | Works but harder to debug if frontend breaks mid-pitch |

### Option C — htmx + sse-swap (no JS)

**Approach:** Server emits HTML fragments, htmx swaps them into the DOM. Zero JavaScript.

| Criterion | Score | Reasoning |
|---|---|---|
| Elegant | 4 | Declarative, idiomatic for SSE |
| Efficient | 3 | More server-side rendering work |
| Effective | 3 | External CDN dependency = single point of failure mid-demo |

**RECOMMENDED: Option A.** Modular separation, no external CDN dependency, vanilla frontend that's easy to debug, ReviewStage stays backward-compatible, all 60 existing tests pass unchanged.

---

## Critic Review (RALPLAN, self-applied)

**Verdict: APPROVE with 8 addressed concerns. No critical flaws.**

| # | Concern | Severity | Resolution |
|---|---|---|---|
| 1 | SSE connection drops on flaky wifi | High | EventSource auto-reconnects; broker pushes full state on reconnect (D9) |
| 2 | Approve clicked before gate registered | Medium | GateRegistry creates events lazily on first call from EITHER side; order-independent |
| 3 | Browser refresh mid-run loses local state | Medium | `/api/state` returns full task list with all events; JS hydrates on load before subscribing |
| 4 | Two SSE subscribers diverging | Low | Each subscriber has its own queue; broker fans out sequentially |
| 5 | macOS firewall prompt on first launch | Medium | Ben clicks Allow once; documented in README |
| 6 | ReviewStage extension breaks existing tests | Low | Default `gate_provider=None` → falls through to `input()` → tests use `AGENTMES_AUTO_APPROVE=1` skip |
| 7 | Static path resolution from different cwd | Low | Use `Path(__file__).parent.parent.parent / "web"` absolute resolution |
| 8 | Pipeline relaunch state cleanup | Medium | Each `/api/launch` builds fresh tasks + fresh stubs + resets GateRegistry |

---

## Tasks

### Task 1: Add `fastapi` dep + scaffold `agent_mes/web/` package
**Objective:** Stand up the web package skeleton and the one new dep so subsequent tasks have somewhere to drop files.
**Complexity:** Simple
**Dependencies:** None
**Files to change:**
- `pyproject.toml` (add `fastapi>=0.115` to dependencies)
- `agent_mes/web/__init__.py` (new, empty)
**Acceptance criteria:**
- `pip install -e ".[dev]"` installs fastapi cleanly
- `python -c "from agent_mes import web; import fastapi, sse_starlette, uvicorn; print('ok')"` succeeds
**Test plan:**
- Smoke: import check
**Rollback plan:** `git checkout pyproject.toml && rm -rf agent_mes/web/`
**Blast radius:** None — new package, new dep
**Research needed:** No

---

### Task 2: `agent_mes/web/events.py` — EventBroker
**Objective:** SSE event broker that fans out pipeline events to all connected browser clients.
**Complexity:** Simple
**Dependencies:** Task 1
**Files to change:**
- `agent_mes/web/events.py` (new)
- `tests/test_events.py` (new)
**Acceptance criteria:**
- `class EventBroker` with `subscribe() → asyncio.Queue`, `unsubscribe(q)`, `publish(event, task)` async, `current_state(tasks) → dict` helper
- `publish` serializes StageEvent + MESTask snapshot to a JSON-compatible dict and puts it on every subscriber queue
- Multiple subscribers all receive every event
- Graceful unsubscribe (queue removed from list)
**Test plan:**
- Unit: 1 publisher + 1 subscriber → drain → assert payload shape
- Unit: 1 publisher + 2 subscribers → both receive
- Unit: subscribe → unsubscribe → publish → no error, no delivery
**Rollback plan:** `rm agent_mes/web/events.py tests/test_events.py`
**Blast radius:** Server depends on this
**Research needed:** No

---

### Task 3: `agent_mes/web/gates.py` — GateRegistry
**Objective:** Per-task asyncio.Event registry so the ReviewStage human gate can be set by browser POSTs.
**Complexity:** Simple
**Dependencies:** Task 1
**Files to change:**
- `agent_mes/web/gates.py` (new)
- `tests/test_gates.py` (new)
**Acceptance criteria:**
- `class GateRegistry` with `register(task_id) → asyncio.Event`, `approve(task_id) → None`, `wait(task_id, timeout=300) → bool`, `reset() → None`
- `approve` and `wait` are order-independent: approve-then-wait works AND wait-then-approve works
- `reset` clears all events (used on `POST /api/launch`)
- `wait` returns True on approval, False on timeout
**Test plan:**
- Unit: approve before wait → wait returns True immediately
- Unit: wait before approve → unblocks when approved
- Unit: timeout returns False
- Unit: reset clears state
**Rollback plan:** `rm agent_mes/web/gates.py tests/test_gates.py`
**Blast radius:** ReviewStage gate provider depends on this
**Research needed:** No

---

### Task 4: Extend `agent_mes/stages/review.py` with optional `gate_provider`
**Objective:** Add the one surgical extension so ReviewStage can satisfy human gates via the GateRegistry instead of `input()`.
**Complexity:** Simple
**Dependencies:** Task 1
**Files to change:**
- `agent_mes/stages/review.py`
**Acceptance criteria:**
- Constructor signature: `def __init__(self, redis, context, gate_provider=None)`
- `gate_provider` is `Callable[[HumanGate], Awaitable[bool]] | None`
- `_await_human(gate)` calls `await self.gate_provider(gate)` if provider is set, otherwise falls through to existing `input()` / `AGENTMES_AUTO_APPROVE=1` logic
- **Default behavior unchanged** — all 60 existing tests pass without modification
**Test plan:**
- Unit: existing `tests/test_review_stage.py` continues to pass
- Unit: new test passes a stub `gate_provider` and verifies it's called
- Smoke: full test suite green (`AGENTMES_AUTO_APPROVE=1 pytest -x`)
**Rollback plan:** `git checkout agent_mes/stages/review.py`
**Blast radius:** ReviewStage is on the critical path; backward-compat is mandatory
**Research needed:** No

---

### Task 5: `agent_mes/web/server.py` — FastAPI app
**Objective:** The HTTP + SSE surface that drives the web UI.
**Complexity:** Moderate
**Dependencies:** Tasks 2, 3, 4
**Files to change:**
- `agent_mes/web/server.py` (new)
**Acceptance criteria:**
- FastAPI app with these routes:
  - `GET /api/state` → JSON `{tasks: [...], running: bool}`
  - `POST /api/launch` → 409 if already running; otherwise resets GateRegistry, builds fresh tasks + fresh stubs, kicks off `pipeline.run_parallel` as a background task, returns `{status: 'launched'}`
  - `POST /api/approve/{task_id}` → calls `gates.approve(task_id)`, returns `{status: 'approved'}`
  - `GET /api/events` → SSE stream; first message is `current_state` snapshot, then live events from broker subscription
  - `GET /` → serves `web/index.html`
  - `GET /replay` → serves `web/replay.html`
  - Static files (`/style.css`, `/app.js`, `/full-demo.cast`) served from `web/`
- Static dir resolved via `Path(__file__).parent.parent.parent / "web"`
- All event publishing routed through a single `EventBroker` instance (module-level)
- Pipeline built with the GateRegistry-backed gate_provider for ReviewStage
**Test plan:**
- Unit: `test_web.py` uses FastAPI TestClient to hit each endpoint
- Integration: launch → consume SSE → assert events fire in order → approve via /api/approve → assert task reaches merged
**Rollback plan:** `rm agent_mes/web/server.py tests/test_web.py`
**Blast radius:** This IS the web demo
**Research needed:** No

---

### Task 6: `agent_mes/cli.py` — add `agent-mes web` command
**Objective:** New CLI subcommand that boots the FastAPI app via uvicorn.
**Complexity:** Simple
**Dependencies:** Task 5
**Files to change:**
- `agent_mes/cli.py`
**Acceptance criteria:**
- New `@app.command()` named `web` that calls `uvicorn.run("agent_mes.web.server:app", host="0.0.0.0", port=8000, log_level="info")`
- Prints the URL on startup: `http://100.85.105.99:8000` (the Mini's Tailscale IP) AND `http://localhost:8000`
- Existing `agent-mes demo` command UNCHANGED
- `agent-mes --help` shows both `demo` and `web` subcommands
**Test plan:**
- Smoke: `python -m agent_mes web --help` exits 0
- Smoke: `timeout 2 python -m agent_mes web` boots and exits cleanly
**Rollback plan:** `git checkout agent_mes/cli.py`
**Blast radius:** Entry point — terminal `demo` must keep working
**Research needed:** No

---

### Task 7: `web/index.html` + `web/style.css` + `web/app.js` — frontend
**Objective:** The live kanban frontend that consumes the SSE stream and renders cards in real time.
**Complexity:** Moderate
**Dependencies:** None (parallel to backend)
**Files to change:**
- `web/index.html` (overwrite — replaces the asciinema-only page)
- `web/style.css` (new)
- `web/app.js` (new)
**Acceptance criteria:**
- `index.html`: header (title + state indicator + Launch button) + `<main class="board">` with 7 `<div class="column" data-stage="...">` containers
- Page load: fetch `/api/state`, render initial cards in their `current_stage` columns
- `EventSource('/api/events')`: on each message, find card by id, update content (or move to new column if `current_stage` changed)
- Card body: title (with type icon ⚙/✉), then either pre-launch raw_input OR detailed changelog grouped by stage with stage headers, action lines, indented metadata, indented artifacts
- Inline `[APPROVE TKT-XXX]` button appears when card is `blocked`; click POSTs `/api/approve/{task_id}`
- Dark theme matching the existing asciinema page (#0b0d12 bg, monospace fonts)
- CSS transitions when cards move between columns (0.3s ease-out)
- Launch button POSTs `/api/launch`, disables itself during run, re-enables when both tickets reach merged
**Test plan:**
- Smoke: `curl -sf http://localhost:8000/` returns HTML containing "AgentMES" and 7 column data-attributes
- Visual: open in browser, click launch, both cards animate through columns, click both approve buttons, both reach DEPLOY
**Rollback plan:** `git checkout web/`
**Blast radius:** This IS the live demo surface
**Research needed:** No

---

### Task 8: `web/replay.html` — move existing asciinema page
**Objective:** Preserve the asciinema fallback as a secondary URL.
**Complexity:** Simple
**Dependencies:** Task 7
**Files to change:**
- `web/replay.html` (new — content from old `web/index.html`)
**Acceptance criteria:**
- The asciinema-player CDN-embedded page now lives at `/replay`
- The `full-demo.cast` reference still resolves
- Browser can play back the cast at the new URL
**Test plan:**
- Smoke: `curl -sf http://localhost:8000/replay | grep -q asciinema-player`
**Rollback plan:** `rm web/replay.html`
**Blast radius:** Backup demo surface
**Research needed:** No

---

### Task 9: `tests/test_web.py` — backend integration smoke
**Objective:** Verify the FastAPI surface end-to-end via TestClient including the launch + approve + SSE event flow.
**Complexity:** Moderate
**Dependencies:** Task 5
**Files to change:**
- `tests/test_web.py` (new)
**Acceptance criteria:**
- `test_state_endpoint_returns_initial_tasks`: GET /api/state → 2 tasks in PLAN, raw_input visible
- `test_launch_starts_pipeline`: POST /api/launch → 200; second POST → 409
- `test_launch_then_consume_events`: launch + open SSE stream + drain events → both tickets eventually reach merged
- `test_approve_unblocks_review_gate`: launch + wait for gate event + POST /api/approve/{id} → task progresses to merged
- `test_relaunch_resets_state`: launch → complete → launch again → fresh task instances, fresh stub state
- `test_get_replay_route`: GET /replay → 200 + asciinema-player content
- All using FastAPI TestClient (not real uvicorn)
- Uses `AGENTMES_AUTO_APPROVE=1` for the auto-approve gate path
- Plus `tests/test_events.py` and `tests/test_gates.py` from T2/T3
**Test plan:**
- Unit + integration: `pytest tests/test_events.py tests/test_gates.py tests/test_web.py -x`
- Full suite: `AGENTMES_AUTO_APPROVE=1 pytest -x` should still pass all 60 existing tests + new web tests = ~75 tests
**Rollback plan:** `rm tests/test_web.py tests/test_events.py tests/test_gates.py`
**Blast radius:** This is the web layer's gate
**Research needed:** No

---

### Task 10: README + Makefile + final smoke
**Objective:** Document the new web surface, update the Makefile to launch uvicorn, run a final manual smoke.
**Complexity:** Simple
**Dependencies:** Task 9
**Files to change:**
- `README.md`
- `Makefile`
**Acceptance criteria:**
- README has new section "Web UI" documenting `agent-mes web`, `make web`, the URL, the macOS firewall prompt, and the `/replay` fallback
- README mentions both surfaces (terminal `agent-mes demo` AND web `agent-mes web`) and the architectural insight (one pipeline, two renderers)
- `Makefile` `web` target replaced: now runs `$(PY) -m agent_mes web` instead of `python -m http.server`
- New `Makefile` target `web-smoke` boots the server, curls /api/state, kills the server
- README note that the existing `recordings/full-demo.cast` is still used for `/replay`
**Test plan:**
- Smoke: `make web-smoke` exits 0
- Smoke: `agent-mes --help` shows both demo and web commands
- Manual: visit `http://100.85.105.99:8000` from MBP, click Launch, click both Approve, both cards reach DEPLOY
**Rollback plan:** `git checkout README.md Makefile`
**Blast radius:** Docs + entry point
**Research needed:** No

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| SSE connection drops on flaky wifi mid-demo | High | EventSource auto-reconnects; broker pushes full state on reconnect (T5 acceptance) |
| macOS firewall prompts on first launch | Medium | Ben clicks Allow once; documented in README (T10) |
| ReviewStage extension breaks existing tests | High | Default `gate_provider=None` → existing path → all 60 tests stay green; T4 verify is full suite run |
| Browser refresh mid-pipeline | Medium | `/api/state` rehydrates; T9 covers refresh-safe behavior |
| Pipeline relaunch leaves stale state | Medium | Each launch builds fresh tasks + stubs + resets GateRegistry; T9 covers |
| Static path resolution from different cwd | Low | Absolute path via `Path(__file__).parent.parent.parent / "web"` |
| Approve before gate registered (race) | Low | GateRegistry is order-independent; T3 covers |
| 2-hour budget tight | Medium | 10 small tasks, parallelize T7 (frontend) with T2-T5 (backend); cut T8 if running long |

## Research Notes

N/A — research gated OUT in the args (FastAPI/SSE patterns are well-known, codebase use is minimal scope, no new external sponsor APIs).

Reference materials in the existing repo:
- Master spec: `docs/specs/agentmes.md`
- Pipeline source: `agent_mes/pipeline.py` (events_callback hook)
- Existing dashboard pattern: `agent_mes/ui/dashboard.py`
- Existing tests: `tests/test_pipeline.py`, `tests/test_review_stage.py`
- Tailscale IP: `100.85.105.99`
