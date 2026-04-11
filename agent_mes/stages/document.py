"""Stage 6 — Document. Generate a decision log from task.events and write
it to long-term memory (Redis) so future Plan stages can retrieve it.
"""

from __future__ import annotations

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

        # Build decision log from events
        log_lines = [f"Task: {task.id} ({task.type.value})", f"Intent: {task.intent}"]
        for ev in task.events:
            log_lines.append(f"  [{ev.stage.value}] {ev.agent}: {ev.action}")
        decision_log = "\n".join(log_lines)

        # Negative constraint: if Stage 5 caught a drift, mark this lesson as a "don't repeat"
        had_drift = any(
            ev.metadata.get("status") == "DRIFT" for ev in task.events
        )

        lesson_id = await self.redis.write_lesson(
            text=decision_log,
            topics=[task.type.value, "task_completion"],
            user_id=task.requester,
            negative_constraint=had_drift,
        )

        event = self._emit_event(
            task=task,
            agent=self.AGENT,
            action=f"lesson written: {lesson_id}",
            metadata={
                "lesson_id": lesson_id,
                "negative_constraint": had_drift,
                "status": "PASS",
            },
            artifacts=[
                Artifact(type="memory", ref=lesson_id, summary="long-term lesson"),
            ],
        )
        return [event]
