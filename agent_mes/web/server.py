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

from fastapi import FastAPI, HTTPException
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
from agent_mes.web.events import EventBroker, _state_payload, _task_payload
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


# ─── FastAPI app ────────────────────────────────────────────────────────────


app = FastAPI(title="AgentMES")
state = WebState()
ensure_artifacts_dir()


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    return {
        "running": state.running,
        "tasks": [_task_payload(t) for t in state.tasks],
    }


async def _broadcast_state() -> None:
    """Push the current task list to every SSE subscriber."""
    payload = _state_payload(state.tasks)
    for q in list(state.broker._subscribers):  # noqa: SLF001
        await q.put(payload)


@app.post("/api/launch/{task_id}")
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


@app.post("/api/reset")
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


@app.post("/api/approve/{task_id}")
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


@app.post("/api/feedback/{task_id}")
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
async def events() -> EventSourceResponse:
    queue = state.broker.subscribe()

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
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
</head><body>
<div class="breadcrumb"><a href="/">← board</a> · {html.escape(task_id)} · {html.escape(stage)}</div>
{content_html}
<script>
  const RAW = {inline_md_literal};
  if (RAW !== null) {{
    document.getElementById("content").innerHTML = marked.parse(RAW);
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
