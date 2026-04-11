"""Pipeline — wires the 7 stages and drives a task through them in sequence.

Each stage's events are forwarded to an `events_callback` so the dashboard
can re-render the kanban in real time. Run two tasks in parallel via
`run_parallel` for the demo's two-card flow.
"""

from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable

from agent_mes.schema import MESTask, StageEnum, StageEvent
from agent_mes.stages.base import BaseStage

EventsCallback = Callable[[StageEvent, MESTask], None] | Callable[[StageEvent, MESTask], Awaitable[None]]

# Visible dwell (in seconds) between stages so cards stay readable in the
# live kanban. Override with AGENTMES_STAGE_DWELL for faster headless runs.
STAGE_DWELL_SECONDS = float(os.environ.get("AGENTMES_STAGE_DWELL", "2.0"))


class Pipeline:
    """Drives MESTasks through all 7 stages with event fan-out."""

    def __init__(
        self,
        plan: BaseStage,
        design: BaseStage,
        build: BaseStage,
        test: BaseStage,
        review: BaseStage,
        document: BaseStage,
        deploy: BaseStage,
        events_callback: EventsCallback | None = None,
    ) -> None:
        self.stages: list[BaseStage] = [plan, design, build, test, review, document, deploy]
        self.events_callback = events_callback
        self._lock = asyncio.Lock()  # serializes callback invocations from parallel tasks
        # Hand each stage a back-reference so _emit_event can stream the
        # event to the events_callback the moment it happens — not after
        # execute() returns. This is what unblocks the ReviewStage hang:
        # drift events land in the browser while the gate is still open.
        for stage in self.stages:
            stage._pipeline = self  # noqa: SLF001 — pipeline-stage contract

    async def run(self, task: MESTask) -> MESTask:
        task.status = "running"
        last_idx = len(self.stages) - 1
        for idx, stage in enumerate(self.stages):
            try:
                await stage.execute(task)
            except Exception as exc:  # noqa: BLE001 — convert to event, never crash the demo
                fail_event = StageEvent(
                    stage=stage.STAGE,
                    agent="pipeline",
                    action=f"FAIL: {type(exc).__name__}: {str(exc)[:50]}",
                    metadata={"status": "FAIL"},
                )
                task.events.append(fail_event)
                await self._fire(fail_event, task)
                task.status = "killed"
                return task

            if task.status == "killed":
                return task

            # Hold the card in the just-finished lane long enough for the
            # audience to read it, then let the next stage advance it.
            if idx < last_idx and STAGE_DWELL_SECONDS > 0:
                await asyncio.sleep(STAGE_DWELL_SECONDS)

        task.status = "merged"
        task.current_stage = StageEnum.DEPLOY
        return task

    async def run_parallel(self, tasks: list[MESTask]) -> list[MESTask]:
        return await asyncio.gather(*(self.run(t) for t in tasks))

    async def _fire(self, event: StageEvent, task: MESTask) -> None:
        """Forward one StageEvent to the registered callback. Called by
        BaseStage._emit_event **and** by run() on pipeline-level failures."""
        if self.events_callback is None:
            return
        async with self._lock:
            result = self.events_callback(event, task)
            if asyncio.iscoroutine(result):
                await result
