"""Stage 6 — Document. Generate a decision log from task.events and write
it to long-term memory (Redis) so future Plan stages can retrieve it.
"""

from __future__ import annotations

import asyncio

from agent_mes.artifacts import render_and_save
from agent_mes.interfaces import RedisMemoryProtocol
from agent_mes.schema import Artifact, MESTask, StageEnum, StageEvent
from agent_mes.stages.base import BaseStage


class DocumentStage(BaseStage):
    STAGE = StageEnum.DOCUMENT
    AGENT = "Redis"

    def __init__(self, redis: RedisMemoryProtocol) -> None:
        self.redis = redis

    async def execute(self, task: MESTask) -> list[StageEvent]:
        task.current_stage = StageEnum.DOCUMENT
        events: list[StageEvent] = []

        events.append(
            await self._emit_event(
                task=task,
                agent="Redis",
                action=f"composing decision log from {len(task.events)} events",
                metadata={"event_count": len(task.events), "status": "RUN"},
            )
        )
        await asyncio.sleep(0.7)

        # Build decision log from events
        log_lines = [f"Task: {task.id} ({task.type.value})", f"Intent: {task.intent}"]
        for ev in task.events:
            log_lines.append(f"  [{ev.stage.value}] {ev.agent}: {ev.action}")
        decision_log = "\n".join(log_lines)

        # Negative constraint: if Stage 5 caught a drift, mark this lesson as a "don't repeat"
        had_drift = any(
            ev.metadata.get("status") == "DRIFT" for ev in task.events
        )

        events.append(
            await self._emit_event(
                task=task,
                agent="Redis",
                action=(
                    "tagging lesson as don't-repeat (drift seen)"
                    if had_drift
                    else f"tagging lesson → topics: {task.type.value}, task_completion"
                ),
                metadata={
                    "topics": [task.type.value, "task_completion"],
                    "negative_constraint": had_drift,
                    "status": "RUN",
                },
            )
        )
        await asyncio.sleep(0.7)

        lesson_id = await self.redis.write_lesson(
            text=decision_log,
            topics=[task.type.value, "task_completion"],
            user_id=task.requester,
            negative_constraint=had_drift,
        )

        events.append(
            await self._emit_event(
                task=task,
                agent="Redis",
                action=f"lesson written: {lesson_id}",
                metadata={
                    "lesson_id": lesson_id,
                    "log_bytes": len(decision_log),
                    "negative_constraint": had_drift,
                    "status": "PASS",
                },
                artifacts=[
                    Artifact(type="memory", ref=lesson_id, summary="long-term lesson"),
                ],
            )
        )
        events[-1].artifacts.append(render_and_save(task, "document"))
        await asyncio.sleep(0.6)
        return events
