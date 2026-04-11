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
import json
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from agent_mes.demo.fake_slack import FAKE_SLACK
from agent_mes.integrations.codex import CodexReplayBuilder
from agent_mes.integrations.stubs.blaxel import StubBlaxelVerifier
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
        self.running: bool = False
        self.pipeline_task: asyncio.Task | None = None
        self._reset_tasks()

    def _reset_tasks(self) -> None:
        """Build fresh MESTask instances from the demo fixtures."""
        self.tasks = [_new_task("TKT-001"), _new_task("TKT-002")]

    def reset(self) -> None:
        """Wipe state for a fresh launch."""
        self.gates.reset()
        self._reset_tasks()
        self.running = False
        self.pipeline_task = None


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


def _build_pipeline(state: WebState) -> Pipeline:
    """Construct the pipeline with the GateRegistry-backed gate_provider so
    ReviewStage's HumanGate is satisfied by browser POSTs to /api/approve."""
    redis = StubRedisMemory()
    context = StubContextRetriever()
    blaxel = StubBlaxelVerifier()

    async def gate_provider(gate: HumanGate) -> bool:
        # The gate.prompt contains the task id implicitly through the stage
        # context, but we need the explicit task_id. ReviewStage's gate
        # creation passes a HumanGate without task_id directly, so we look
        # up which task is currently blocked. There is exactly one blocked
        # task per gate fire because pipeline.run_parallel runs each task
        # sequentially through stages and only one is paused at a time
        # per task instance.
        # Find the task currently in REVIEW with status=blocked.
        candidates = [t for t in state.tasks if t.status == "blocked"]
        if not candidates:
            # Defensive: should never hit this in practice
            await asyncio.sleep(0.05)
            return True
        target = candidates[0]
        return await state.gates.wait(target.id, timeout=300.0)

    pipeline = Pipeline(
        plan=PlanStage(wordware=WordwarePlanner(mode="stub")),
        design=DesignStage(redis=redis, context=context),
        build=BuildStage(codex=CodexReplayBuilder(speed=1000.0)),
        test=TestStage(blaxel=blaxel),
        review=ReviewStage(redis=redis, context=context, gate_provider=gate_provider),
        document=DocumentStage(redis=redis),
        deploy=DeployStage(redis=redis, dry_run=True),
        events_callback=state.broker.publish,
    )
    return pipeline


# ─── FastAPI app ────────────────────────────────────────────────────────────


app = FastAPI(title="AgentMES")
state = WebState()


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    return {
        "running": state.running,
        "tasks": [_task_payload(t) for t in state.tasks],
    }


@app.post("/api/launch")
async def launch() -> dict[str, str]:
    if state.running:
        raise HTTPException(status_code=409, detail="pipeline already running")
    state.reset()
    state.running = True
    pipeline = _build_pipeline(state)
    # Push fresh state to all subscribers so the browser sees the reset
    payload = _state_payload(state.tasks)
    for q in list(state.broker._subscribers):  # noqa: SLF001
        await q.put(payload)

    async def _run() -> None:
        try:
            await pipeline.run_parallel(state.tasks)
        finally:
            state.running = False

    state.pipeline_task = asyncio.create_task(_run())
    return {"status": "launched"}


@app.post("/api/approve/{task_id}")
async def approve(task_id: str) -> dict[str, str]:
    state.gates.approve(task_id)
    return {"status": "approved", "task_id": task_id}


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
