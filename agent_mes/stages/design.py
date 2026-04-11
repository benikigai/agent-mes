"""Stage 2 — Design. Hydrate context_bundle (Context Retriever) and
memory_provenance (Redis Memory) in parallel. Emits THREE StageEvents
representing the Opus + Codex + Gemini sub-agents.
"""

from __future__ import annotations

import asyncio

from agent_mes.interfaces import ContextRetrieverProtocol, RedisMemoryProtocol
from agent_mes.schema import MemoryProvenance, MESTask, StageEnum, StageEvent
from agent_mes.stages.base import BaseStage


class DesignStage(BaseStage):
    STAGE = StageEnum.DESIGN
    AGENTS = ["Opus 4.6", "Codex", "Gemini"]

    def __init__(
        self,
        redis: RedisMemoryProtocol,
        context: ContextRetrieverProtocol,
    ) -> None:
        self.redis = redis
        self.context = context

    async def execute(self, task: MESTask) -> list[StageEvent]:
        task.current_stage = StageEnum.DESIGN

        # Hydrate memory + ground truth in parallel
        memories, service = await asyncio.gather(
            self.redis.hydrate(query=task.intent, session_id=task.id),
            self.context.query_entity("service", "svc_auth"),
        )

        # Populate task with the hydrated state
        task.memory_provenance = [
            MemoryProvenance(
                text=m["text"],
                confidence=m["confidence"],
                source=m["source"],
            )
            for m in memories
        ]
        task.context_bundle = {"service": service, "memories_retrieved": len(memories)}

        events: list[StageEvent] = []

        events.append(
            self._emit_event(
                task=task,
                agent="Opus 4.6",
                action="sketched architecture",
                metadata={
                    "memory_count": len(memories),
                    "service": service["name"],
                    "status": "PASS",
                },
            )
        )

        events.append(
            self._emit_event(
                task=task,
                agent="Codex",
                action="scaffolded files in worktree",
                metadata={
                    "files": "auth/middleware.py, tests/auth/" if task.type.value == "code" else "drafts/email.md",
                    "status": "PASS",
                },
            )
        )

        events.append(
            self._emit_event(
                task=task,
                agent="Gemini",
                action="reviewed sketch",
                metadata={
                    "verdict": "approved",
                    "status": "PASS",
                },
            )
        )

        return events
