"""FastAPI app — the HTTP + SSE surface that drives the web kanban.

The pipeline is built once per /api/launch with fresh stub backends so
each demo run starts from a clean state. Pipeline events flow through a
module-level EventBroker; SSE clients subscribe to the broker and receive
both an initial state snapshot and live event updates.

Static files served from web/ at the repo root, resolved absolutely so
the server works regardless of cwd.
"""

from __future__ import annotations

import asyncio
import html
import json
import os
from pathlib import Path
from typing import Any, AsyncIterator

import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from agent_mes.artifacts import (
    ARTIFACTS_ROOT,
    clear_artifacts,
    ensure_artifacts_dir,
    read_stage_artifact,
)
from agent_mes.demo.fake_slack import FAKE_SLACK
from agent_mes.integrations.codex import CodexReplayBuilder
from agent_mes.integrations.stubs.blaxel import StubBlaxelVerifier

try:
    # Probe the REAL Blaxel SDK, not just our wrapper. blaxel_live.py imports
    # the SDK lazily inside a method, so the wrapper module imports fine even
    # when the SDK is absent — which made _HAS_BLAXEL_LIVE always True and let
    # /api/mode claim blaxel_live:true while TestStage silently ran the stub.
    # Gating on the real SDK keeps the badge AND the verifier selection honest.
    import blaxel.core  # noqa: F401
    from agent_mes.integrations.blaxel_live import BlaxelLiveVerifier  # noqa: F401
    _HAS_BLAXEL_LIVE = True
except Exception:  # noqa: BLE001
    _HAS_BLAXEL_LIVE = False

try:
    from agent_mes.integrations.plushpalace_context import (
        build_plushpalace_adapter_or_none,
    )
    _HAS_PLUSHPALACE = True
except Exception:  # noqa: BLE001
    _HAS_PLUSHPALACE = False

    def build_plushpalace_adapter_or_none():  # type: ignore[misc]
        return None
from agent_mes.integrations.stubs.context_retriever import StubContextRetriever
from agent_mes.integrations.stubs.redis_memory import StubRedisMemory
from agent_mes.integrations.wordware import WordwarePlanner
from agent_mes.pipeline import Pipeline
from agent_mes.schema import HumanGate, MESTask, TicketType
from agent_mes.stages.build import BuildStage
from agent_mes.stages.deploy import DeployStage
from agent_mes.stages.design import DesignStage
from agent_mes.stages.document import DocumentStage
from agent_mes.stages.plan import PlanStage
from agent_mes.stages.review import ReviewStage
from agent_mes.stages.test import TestStage
from agent_mes.web.events import (
    EventBroker,
    SubscriberLimitExceeded,
    _state_payload,
    _task_payload,
)
from agent_mes.web.gates import GateRegistry

# Repo root → /Users/elias/code/blaxel-codex-redis-hackathon
# server.py → agent_mes/web/server.py → parent.parent.parent = repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = REPO_ROOT / "web"


# ─── module-level state ─────────────────────────────────────────────────────


class WebState:
    """All mutable state for the web server lives here."""

    def __init__(self) -> None:
        self.broker = EventBroker()
        self.gates = GateRegistry()
        self.tasks: list[MESTask] = []
        # Per-task running flags so each card's Start button can fire
        # independently without blocking the other ticket.
        self.running_task_ids: set[str] = set()
        self.pipeline_tasks: dict[str, asyncio.Task] = {}
        self._reset_tasks()

    def _reset_tasks(self) -> None:
        """Build fresh MESTask instances from the demo fixtures.

        Order matters for the live demo: the SIMPLE postmortem (TKT-002)
        renders in the left-most card so the natural left-to-right click
        order is simple → complex.
        """
        self.tasks = [_new_task("TKT-002"), _new_task("TKT-001")]

    @property
    def running(self) -> bool:
        return bool(self.running_task_ids)

    def reset(self) -> None:
        """Wipe state for a fresh launch — pipeline tasks must already be
        cancelled by the caller before calling this."""
        self.gates.reset()
        self.running_task_ids.clear()
        self.pipeline_tasks.clear()
        self._reset_tasks()


_SIMPLE_HINTS = ("draft", "postmortem", "email", "summary", "report", "send", "notify")


def _pre_classify(raw_text: str) -> TicketType:
    text_lower = raw_text.lower()
    if any(k in text_lower for k in _SIMPLE_HINTS):
        return TicketType.SIMPLE
    return TicketType.CODE


def _new_task(ticket_id: str) -> MESTask:
    f = FAKE_SLACK[ticket_id]
    return MESTask(
        id=ticket_id,
        type=_pre_classify(f["raw_text"]),
        intent="",
        raw_input=f["raw_text"],
        requester=f["requester"],
        source=f["channel"],
    )


def _build_pipeline(state: WebState, target_task_id: str) -> Pipeline:
    """Construct the pipeline with the GateRegistry-backed gate_provider so
    both ReviewStage and DeployStage HumanGates can be satisfied by browser
    POSTs to /api/approve.

    Each launched ticket gets its own Pipeline instance scoped to a single
    task_id so the gate_provider never confuses which card is waiting when
    multiple cards are in flight. Gate keys are namespaced as
    ``task_id:stage`` so Review's gate and Deploy's gate don't collide on
    the same asyncio.Event.
    """
    # Prefer the plushpalace-world synthetic context graph if the package
    # is importable. The adapter satisfies BOTH the RedisMemoryProtocol and
    # the ContextRetrieverProtocol — one object, two roles, pointing at the
    # same YAML-backed store so hydration and verification stay consistent.
    pp_adapter = build_plushpalace_adapter_or_none()
    if pp_adapter is not None:
        redis = pp_adapter
        context = pp_adapter
    else:
        redis = StubRedisMemory()
        context = StubContextRetriever()

    # Prefer real Blaxel when the SDK is importable and AGENTMES_BLAXEL_STUB
    # is not set. Any exception during the real path will be caught by
    # TestStage — we still build the live verifier here optimistically.
    if _HAS_BLAXEL_LIVE and os.environ.get("AGENTMES_BLAXEL_STUB") != "1":
        blaxel = BlaxelLiveVerifier()
    else:
        blaxel = StubBlaxelVerifier()

    async def gate_provider(gate: HumanGate) -> bool:
        key = f"{target_task_id}:{gate.stage.value}"
        return await state.gates.wait(key, timeout=300.0)

    pipeline = Pipeline(
        plan=PlanStage(wordware=WordwarePlanner(mode="stub")),
        design=DesignStage(redis=redis, context=context),
        build=BuildStage(codex=CodexReplayBuilder(speed=1000.0)),
        test=TestStage(blaxel=blaxel),
        review=ReviewStage(redis=redis, context=context, gate_provider=gate_provider),
        document=DocumentStage(redis=redis),
        deploy=DeployStage(
            redis=redis,
            # Real PRs land when AGENTMES_OPEN_REAL_PR=1 is set in the
            # server's environment. Default is dry-run so rehearsals
            # don't spam the repo.
            dry_run=os.environ.get("AGENTMES_OPEN_REAL_PR") != "1",
            gate_provider=gate_provider,
        ),
        events_callback=state.broker.publish,
    )
    return pipeline


# ─── rate limiting ──────────────────────────────────────────────────────────

# App-level limiter on the mutation endpoints. The public deployment sits behind
# a Cloudflare tunnel, so every request arrives from 127.0.0.1 — request.client
# is useless for per-visitor limiting. Cloudflare sets CF-Connecting-IP to the
# real visitor IP; we key on that (falling back through XFF then the peer).
# A Cloudflare front-door rule could layer on top, but this is self-contained
# and protects the Mini regardless of the front door.
RATE_LIMIT_MAX = 30  # mutations per window per visitor (generous for live demo)
RATE_LIMIT_WINDOW = 60.0  # seconds


class RateLimiter:
    """Sliding-window per-key limiter. Memory-bounded by opportunistic prune."""

    def __init__(self, max_events: int, window_s: float) -> None:
        self.max_events = max_events
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float) -> bool:
        cutoff = now - self.window_s
        dq = self._hits[key]
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= self.max_events:
            return False
        dq.append(now)
        if len(self._hits) > 4096:  # bound memory under a key-flood
            for k in [k for k, d in self._hits.items() if not d or d[-1] < cutoff]:
                del self._hits[k]
        return True


_rate_limiter = RateLimiter(RATE_LIMIT_MAX, RATE_LIMIT_WINDOW)


_LOOPBACK = {"127.0.0.1", "::1"}


def _client_key(request: Request) -> str:
    """Identify the visitor for rate limiting.

    Forwarding headers (CF-Connecting-IP / X-Forwarded-For) are only honored
    when the immediate peer is loopback — i.e. the request came through the
    local cloudflared tunnel or tailscale-serve, which set those headers
    truthfully. A direct client could spoof them, so for any non-loopback
    peer we key on the real peer address and ignore the headers entirely.
    """
    peer = request.client.host if request.client else "unknown"
    if peer in _LOOPBACK:
        forwarded = (
            request.headers.get("cf-connecting-ip")
            or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        )
        if forwarded:
            return forwarded
    return peer


def rate_limit(request: Request) -> None:
    """FastAPI dependency — 429s a visitor who exceeds the mutation budget."""
    if not _rate_limiter.allow(_client_key(request), time.monotonic()):
        raise HTTPException(
            status_code=429, detail="rate limit exceeded — slow down a moment"
        )


# ─── FastAPI app ────────────────────────────────────────────────────────────


app = FastAPI(title="AgentMES")
state = WebState()
ensure_artifacts_dir()


@app.on_event("startup")
async def _seed_redis_on_startup() -> None:
    """Best-effort seed plushpalace into Redis at boot. Silent no-op if
    Redis isn't running — the /redis dashboard renders an offline chip
    in that case."""
    try:
        from agent_mes.integrations.redis_backend import (
            connect_or_none,
            seed_plushpalace,
        )

        client = connect_or_none()
        if client is None:
            return
        counts = seed_plushpalace(client)
        total = sum(counts.values())
        print(f"  redis: seeded {total} plushpalace keys across {len(counts)} types")
    except Exception as exc:  # noqa: BLE001
        print(f"  redis: seed failed — {type(exc).__name__}: {str(exc)[:80]}")


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    return {
        "running": state.running,
        "tasks": [_task_payload(t) for t in state.tasks],
    }


@app.get("/api/mode")
async def get_mode() -> dict[str, Any]:
    """Return which integration modes the server is currently running
    in. The browser reads this on boot to decorate the topbar chip."""
    # Live Redis probe so the topbar can show a green "Redis: connected"
    # state when a real Redis instance is reachable.
    redis_connected = False
    redis_dbsize = 0
    try:
        from agent_mes.integrations.redis_backend import connect_or_none

        client = connect_or_none()
        if client is not None:
            redis_connected = True
            redis_dbsize = int(client.dbsize())
    except Exception:  # noqa: BLE001
        pass

    return {
        "real_pr": os.environ.get("AGENTMES_OPEN_REAL_PR") == "1",
        "blaxel_live": _HAS_BLAXEL_LIVE
        and os.environ.get("AGENTMES_BLAXEL_STUB") != "1",
        "plushpalace_context": _HAS_PLUSHPALACE
        and os.environ.get("AGENTMES_USE_PLUSHPALACE") != "0",
        "redis_connected": redis_connected,
        "redis_dbsize": redis_dbsize,
        "github_repo": "benikigai/agent-mes",
    }


async def _broadcast_state() -> None:
    """Push the current task list to every SSE subscriber."""
    state.broker.broadcast(_state_payload(state.tasks))


@app.post("/api/launch/{task_id}", dependencies=[Depends(rate_limit)])
async def launch_one(task_id: str) -> dict[str, str]:
    """Launch a single ticket through the pipeline.

    Each task card has its own Start button; clicks are independent so the
    operator can drive the demo one card at a time.
    """
    target = next((t for t in state.tasks if t.id == task_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"unknown task {task_id}")
    if task_id in state.running_task_ids:
        raise HTTPException(status_code=409, detail=f"{task_id} already running")
    if target.status == "merged":
        raise HTTPException(status_code=409, detail=f"{task_id} already merged")

    state.running_task_ids.add(task_id)
    pipeline = _build_pipeline(state, task_id)

    async def _run() -> None:
        try:
            await pipeline.run(target)
        finally:
            state.running_task_ids.discard(task_id)
            state.pipeline_tasks.pop(task_id, None)

    state.pipeline_tasks[task_id] = asyncio.create_task(_run())
    return {"status": "launched", "task_id": task_id}


@app.post("/api/reset", dependencies=[Depends(rate_limit)])
async def reset_board() -> dict[str, str]:
    """Cancel any in-flight pipeline tasks, rebuild fresh MESTasks, wipe
    stale stage artifacts, and broadcast the reset state to every SSE
    subscriber."""
    for tid, pt in list(state.pipeline_tasks.items()):
        if not pt.done():
            pt.cancel()
            try:
                await pt
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
    state.reset()
    clear_artifacts()
    await _broadcast_state()
    return {"status": "reset"}


@app.post("/api/approve/{task_id}", dependencies=[Depends(rate_limit)])
async def approve(task_id: str) -> dict[str, str]:
    """Approve whichever human gate the task is currently parked at.

    The card can block at Stage 5 (Review) or Stage 7 (Deploy & Maintain).
    We look up the task's current_stage to construct the same namespaced
    gate key the stage's gate_provider is waiting on.
    """
    target = next((t for t in state.tasks if t.id == task_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"unknown task {task_id}")
    stage = target.current_stage.value
    state.gates.approve(f"{task_id}:{stage}")
    return {"status": "approved", "task_id": task_id, "stage": stage}


@app.post("/api/feedback/{task_id}", dependencies=[Depends(rate_limit)])
async def feedback(task_id: str, payload: dict[str, Any]) -> dict[str, str]:
    """Reject the current Review gate and re-route back to Plan with the
    operator's feedback folded into the re-run.

    Cancels the in-flight pipeline task, rebuilds a fresh MESTask but
    preserves ``context_bundle['operator_feedback']`` so PlanStage can
    emit an "incorporating feedback" event at the top of the new run.
    """
    idx = next((i for i, t in enumerate(state.tasks) if t.id == task_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"unknown task {task_id}")

    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="feedback text is required")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="feedback text too long (max 2000 chars)")
    # Neutralize HTML at the trust boundary. This is anonymous, unauthenticated
    # input on the public deployment, and it flows into multiple markdown sinks:
    # the web artifact pages, /output, the GitHub PR body, and the terminal
    # renderer. Escaping here defends every downstream renderer at once; the web
    # pages additionally DOMPurify-sanitize at render time (defense in depth).
    text = html.escape(text)

    # 1. Cancel whatever pipeline task is in flight for this ticket.
    pt = state.pipeline_tasks.pop(task_id, None)
    state.running_task_ids.discard(task_id)
    if pt is not None and not pt.done():
        pt.cancel()
        try:
            await pt
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    # 2. Carry the feedback history forward onto a fresh task instance.
    prior = state.tasks[idx]
    history = list(prior.context_bundle.get("operator_feedback", []) or [])
    history.append(text)

    fresh = _new_task(task_id)
    fresh.context_bundle["operator_feedback"] = history
    state.tasks[idx] = fresh

    # 3. Clear the per-task gate event so the new run's review can block.
    state.gates.reset_task(task_id)

    # 4. Tell the browser immediately that this card has rewound to Plan.
    await _broadcast_state()

    # 5. Launch a fresh pipeline run for the same task_id.
    state.running_task_ids.add(task_id)
    pipeline = _build_pipeline(state, task_id)

    async def _run() -> None:
        try:
            await pipeline.run(fresh)
        finally:
            state.running_task_ids.discard(task_id)
            state.pipeline_tasks.pop(task_id, None)

    state.pipeline_tasks[task_id] = asyncio.create_task(_run())
    return {"status": "rerouted", "task_id": task_id, "feedback_count": str(len(history))}


@app.get("/api/events")
async def events(request: Request) -> EventSourceResponse:
    try:
        queue = state.broker.subscribe(_client_key(request))
    except SubscriberLimitExceeded as exc:
        raise HTTPException(
            status_code=503, detail="too many live connections — retry shortly"
        ) from exc

    async def gen() -> AsyncIterator[dict[str, str]]:
        try:
            # Push initial state so reconnects/refreshes are self-healing
            yield {"data": json.dumps(_state_payload(state.tasks))}
            while True:
                payload = await queue.get()
                yield {"data": json.dumps(payload)}
        except asyncio.CancelledError:
            raise
        finally:
            state.broker.unsubscribe(queue)

    return EventSourceResponse(gen())


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/replay")
async def replay() -> FileResponse:
    return FileResponse(STATIC_DIR / "replay.html")


_ARTIFACT_VIEWER_CSS = """
body { background:#0b0d12; color:#e6e6e6; font-family:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif;
       max-width:860px; margin:40px auto; padding:0 24px; line-height:1.6; }
h1 { color:#4dd0e1; border-bottom:1px solid #2a3040; padding-bottom:10px; }
h2 { color:#4dd0e1; margin-top:28px; }
h3 { color:#e6e6e6; }
code { background:#161922; padding:2px 6px; border-radius:3px;
       font-family:"JetBrains Mono",Menlo,monospace; font-size:0.92em; color:#fbbf24; }
pre { background:#11141c; border:1px solid #2a3040; border-radius:6px; padding:14px;
      overflow-x:auto; font-size:12.5px; line-height:1.5; }
pre code { background:none; padding:0; color:#e6e6e6; }
blockquote { border-left:3px solid #4dd0e1; margin-left:0; padding-left:14px; color:#9aa3b2; }
a { color:#4dd0e1; }
hr { border:none; border-top:1px solid #2a3040; margin:24px 0; }
table { border-collapse:collapse; margin:12px 0; }
td,th { border:1px solid #2a3040; padding:6px 10px; }
th { background:#161922; color:#4dd0e1; }
ul { padding-left:20px; }
li { margin:4px 0; }
.breadcrumb { color:#6f7689; font-family:"JetBrains Mono",Menlo,monospace; font-size:12px; margin-bottom:24px; }
.breadcrumb a { color:#9aa3b2; text-decoration:none; }
.breadcrumb a:hover { color:#4dd0e1; }
.missing { color:#fbbf24; font-family:"JetBrains Mono",Menlo,monospace; font-size:13px; }
"""


_REDIS_DASHBOARD_CSS = """
body { background:#0b0d12; color:#e6e6e6; font-family:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif;
       margin:0; padding:0; line-height:1.5; }
.topbar { padding:16px 28px; border-bottom:1px solid #2a3040; background:#11141c;
          display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
.topbar h1 { margin:0; color:#f87171; font-size:22px; font-weight:700; }
.topbar .sub { color:#9aa3b2; font-size:13px; font-family:"JetBrains Mono",Menlo,monospace; }
.conn-chip { font-family:"JetBrains Mono",Menlo,monospace; font-size:10px; font-weight:700;
             letter-spacing:0.1em; text-transform:uppercase; padding:5px 10px; border-radius:4px;
             border:1px solid; white-space:nowrap; }
.conn-chip.live { color:#0b0d12; border-color:#4ade80; background:#4ade80;
                  box-shadow:0 0 12px rgba(74,222,128,0.35); }
.conn-chip.offline { color:#9aa3b2; border-color:#2a3040; background:#161922; }
.topbar .src { margin-left:auto; color:#4dd0e1; text-decoration:none; font-size:12px;
               font-family:"JetBrains Mono",Menlo,monospace; }
.topbar .src:hover { text-decoration:underline; }
.layout { display:grid; grid-template-columns: 320px 1fr; min-height:calc(100vh - 80px); }
.sidebar { background:#0e1118; border-right:1px solid #2a3040; padding:14px 0; overflow-y:auto;
           max-height:calc(100vh - 80px); }
.sidebar-section { padding:10px 18px 4px; font-family:"JetBrains Mono",Menlo,monospace; font-size:10px;
                   font-weight:700; letter-spacing:0.12em; text-transform:uppercase; color:#6f7689;
                   border-top:1px solid #1f2330; margin-top:6px; }
.sidebar-section:first-of-type { border-top:none; margin-top:0; }
.key-entry { display:block; padding:6px 18px; color:#e6e6e6; text-decoration:none; font-size:12px;
             font-family:"JetBrains Mono",Menlo,monospace; border-left:2px solid transparent; }
.key-entry:hover { background:#161922; border-left-color:#4dd0e1; }
.key-entry.active { background:#161922; border-left-color:#f87171; color:#f87171; }
.key-title { color:#9aa3b2; font-size:10.5px; margin-top:2px; display:block; font-family:sans-serif;
             white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.viewer { padding:24px 32px; overflow-y:auto; max-height:calc(100vh - 80px); }
.viewer h2 { color:#f87171; margin:0 0 6px; font-size:20px; }
.viewer .key-meta { color:#9aa3b2; font-family:"JetBrains Mono",Menlo,monospace; font-size:12px;
                    margin-bottom:20px; padding-bottom:16px; border-bottom:1px dashed #2a3040; }
.viewer .key-meta code { color:#fbbf24; background:#161922; padding:2px 6px; border-radius:3px; }
.viewer .key-meta .cmd { color:#9aa3b2; margin-top:10px; }
.viewer .key-meta .cmd strong { color:#4dd0e1; }
.viewer pre { background:#11141c; border:1px solid #2a3040; border-radius:6px; padding:16px;
              overflow-x:auto; font-family:"JetBrains Mono",Menlo,monospace; font-size:12.5px;
              line-height:1.55; color:#e6e6e6; }
.empty { color:#6f7689; padding:40px; text-align:center; font-style:italic; }
.breadcrumb { color:#6f7689; font-family:"JetBrains Mono",Menlo,monospace; font-size:12px; }
.breadcrumb a { color:#9aa3b2; text-decoration:none; }
.breadcrumb a:hover { color:#4dd0e1; }
.stats-row { display:flex; gap:10px; flex-wrap:wrap; padding:10px 18px 14px; }
.stat { background:#161922; border:1px solid #2a3040; border-radius:4px; padding:8px 12px;
        font-family:"JetBrains Mono",Menlo,monospace; font-size:9px; color:#9aa3b2;
        letter-spacing:0.08em; }
.stat strong { color:#f87171; font-size:16px; display:block; margin-top:2px; letter-spacing:0; }
"""


_PLUSHPALACE_YAML_FILES = {
    "person": "data/people.yaml",
    "vendor": "data/vendors.yaml",
    "product": "data/products.yaml",
    "repository": "data/repos.yaml",
    "incident": "data/incidents.yaml",
    "postmortem": "data/postmortems.yaml",
    "code_change": "data/code.yaml",
    "customer": "data/customers.yaml",
    "email": "data/emails.yaml",
    "lesson": "data/lessons.yaml",
}


@app.get("/redis")
async def redis_dashboard(key: str | None = None) -> HTMLResponse:
    """Live Redis key browser — connects to localhost:6379, SCANs every
    key, GETs the selected value. Shows a "Connected" chip with the URL
    + DBSIZE so the demo proves it's talking to a real Redis, not a
    static fixture."""
    from agent_mes.integrations.redis_backend import (
        DEFAULT_REDIS_URL,
        connect_or_none,
        get_value,
        group_by_type,
        scan_all_keys,
    )

    client = connect_or_none()
    if client is None:
        page = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Redis — offline</title>
<style>{_REDIS_DASHBOARD_CSS}</style></head><body>
<div class="topbar"><h1>Redis</h1>
<span class="conn-chip offline">● offline</span>
<span class="sub">could not reach {DEFAULT_REDIS_URL}</span></div>
<div class="empty" style="padding:60px 40px">
  Redis is not reachable. Start it with <code>brew services start redis</code>
  and re-seed via <code>python -m agent_mes.integrations.redis_backend</code>.
</div></body></html>"""
        return HTMLResponse(page)

    redis_url = os.environ.get("AGENTMES_REDIS_URL") or DEFAULT_REDIS_URL
    try:
        dbsize = client.dbsize()
    except Exception:  # noqa: BLE001
        dbsize = 0
    all_keys = scan_all_keys(client)
    grouped = group_by_type(all_keys)

    selected_key = key if key in all_keys else (all_keys[0] if all_keys else None)
    selected_value = get_value(client, selected_key) if selected_key else None

    # Sidebar — group by type, each link is a real Redis key
    sidebar_html: list[str] = []
    for kind in sorted(grouped.keys()):
        sidebar_html.append(
            f'<div class="sidebar-section">{html.escape(kind)} '
            f'({len(grouped[kind])})</div>'
        )
        for k in grouped[kind]:
            val = get_value(client, k) or {}
            title = str(
                val.get("title") or val.get("name") or val.get("subject") or ""
            )[:55]
            active = "active" if k == selected_key else ""
            title_html = (
                f'<span class="key-title">{html.escape(title)}</span>'
                if title
                else ""
            )
            sidebar_html.append(
                f'<a class="key-entry {active}" href="/redis?key={html.escape(k)}">'
                f'{html.escape(k)}{title_html}</a>'
            )

    # Viewer panel — shows the selected key's value + the exact Redis
    # commands that would retrieve it from the CLI
    if selected_key and selected_value is not None:
        skind = selected_key.split(":", 1)[0]
        yaml_file = _PLUSHPALACE_YAML_FILES.get(skind, f"data/{skind}.yaml")
        gh_url = f"https://github.com/benikigai/plushpalace-world/blob/main/{yaml_file}"
        title = str(
            selected_value.get("title")
            or selected_value.get("name")
            or selected_value.get("subject")
            or selected_key
        )
        viewer_html = f'''
            <div class="breadcrumb"><a href="/">← board</a> · Redis · {html.escape(skind)} · {html.escape(selected_key)}</div>
            <h2>{html.escape(title)}</h2>
            <div class="key-meta">
              <code>{html.escape(selected_key)}</code> ·
              source on GitHub: <a href="{gh_url}" target="_blank" style="color:#4dd0e1">↗ {html.escape(yaml_file)}</a>
              <div class="cmd"><strong>redis-cli GET</strong> "{html.escape(selected_key)}"</div>
            </div>
            <pre><code>{html.escape(json.dumps(selected_value, indent=2, default=str))}</code></pre>
        '''
    elif not all_keys:
        viewer_html = (
            '<div class="empty">Redis is connected but empty. '
            'Run <code>python -m agent_mes.integrations.redis_backend</code> to seed plushpalace.</div>'
        )
    else:
        viewer_html = '<div class="empty">key not found in Redis</div>'

    stats_row = f"""
        <div class="stats-row">
          <div class="stat">DBSIZE<strong>{dbsize}</strong></div>
          <div class="stat">KEY TYPES<strong>{len(grouped)}</strong></div>
          <div class="stat">BACKEND<strong>PLUSHPALACE</strong></div>
        </div>
    """

    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Redis — AgentMES</title>
<style>{_REDIS_DASHBOARD_CSS}</style>
</head><body>
<div class="topbar">
  <h1>Redis</h1>
  <span class="conn-chip live">● CONNECTED</span>
  <span class="sub">{html.escape(redis_url)}</span>
  <a class="src" href="https://github.com/benikigai/plushpalace-world" target="_blank">↗ data source: plushpalace-world</a>
</div>
<div class="layout">
  <div class="sidebar">
    {stats_row}
    {''.join(sidebar_html)}
  </div>
  <div class="viewer">
    {viewer_html}
  </div>
</div>
</body></html>"""
    return HTMLResponse(page)


@app.get("/output/{task_id}")
async def view_output(task_id: str) -> HTMLResponse:
    """Render the drafted email output for SIMPLE tickets (e.g.
    ``.demo/outputs/postmortem-TKT-002.md``) as a dark-themed page so
    operators can click the artifact link and review the actual
    delivered file in the browser."""
    output_path = Path(".demo/outputs") / f"postmortem-{task_id}.md"
    if not output_path.exists():
        content = f'<p class="missing">no output file yet for {html.escape(task_id)} — run the pipeline first</p>'
        raw_literal = "null"
    else:
        content = '<div id="content">rendering…</div>'
        raw_literal = json.dumps(output_path.read_text(encoding="utf-8"))

    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{html.escape(task_id)} output — AgentMES</title>
<style>{_ARTIFACT_VIEWER_CSS}</style>
<script src="/static/vendor/marked.min.js" integrity="sha384-/TQbtLCAerC3jgaim+N78RZSDYV7ryeoBCVqTuzRrFec2akfBkHS7ACQ3PQhvMVi"></script>
<script src="/static/vendor/purify.min.js" integrity="sha384-JEyTNhjM6R1ElGoJns4U2Ln4ofPcqzSsynQkmEc/KGy6336qAZl70tDLufbkla+3"></script>
</head><body>
<div class="breadcrumb"><a href="/">← board</a> · {html.escape(task_id)} · delivered output (<code>.demo/outputs/postmortem-{html.escape(task_id)}.md</code>)</div>
{content}
<script>
  const RAW = {raw_literal};
  if (RAW !== null) {{
    document.getElementById("content").innerHTML = DOMPurify.sanitize(marked.parse(RAW));
  }}
</script>
</body></html>"""
    return HTMLResponse(page)


@app.get("/artifact/{task_id}/{stage}")
async def view_artifact(task_id: str, stage: str) -> HTMLResponse:
    """Render a per-stage markdown artifact as a dark-themed HTML page."""
    body = read_stage_artifact(task_id, stage)
    title = f"{task_id} · {stage}"
    if body is None:
        content_html = (
            f'<p class="missing">no artifact yet for <code>{html.escape(task_id)}</code> · '
            f'<code>{html.escape(stage)}</code> — this stage has not been run, or the board was reset.</p>'
        )
        inline_md_literal = "null"
    else:
        content_html = '<div id="content">rendering…</div>'
        inline_md_literal = json.dumps(body)

    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)} — AgentMES artifact</title>
<style>{_ARTIFACT_VIEWER_CSS}</style>
<script src="/static/vendor/marked.min.js" integrity="sha384-/TQbtLCAerC3jgaim+N78RZSDYV7ryeoBCVqTuzRrFec2akfBkHS7ACQ3PQhvMVi"></script>
<script src="/static/vendor/purify.min.js" integrity="sha384-JEyTNhjM6R1ElGoJns4U2Ln4ofPcqzSsynQkmEc/KGy6336qAZl70tDLufbkla+3"></script>
</head><body>
<div class="breadcrumb"><a href="/">← board</a> · {html.escape(task_id)} · {html.escape(stage)}</div>
{content_html}
<script>
  const RAW = {inline_md_literal};
  if (RAW !== null) {{
    document.getElementById("content").innerHTML = DOMPurify.sanitize(marked.parse(RAW));
  }}
</script>
</body></html>"""
    return HTMLResponse(page)


# Static files for /style.css, /app.js, /full-demo.cast etc.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Convenience: also serve top-level static files at the root for /style.css etc.
@app.get("/style.css")
async def style() -> FileResponse:
    return FileResponse(STATIC_DIR / "style.css")


@app.get("/app.js")
async def app_js() -> FileResponse:
    return FileResponse(STATIC_DIR / "app.js")


@app.get("/full-demo.cast")
async def full_demo_cast() -> FileResponse:
    return FileResponse(STATIC_DIR / "full-demo.cast")
