"""Stage 2 — Design. Hydrate context_bundle (Context Retriever) and
memory_provenance (Redis Memory) in parallel. Emits THREE StageEvents
representing the Opus + Codex + Gemini sub-agents.
"""

from __future__ import annotations

import asyncio

from agent_mes.artifacts import render_and_save
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
        events: list[StageEvent] = []

        events.append(
            await self._emit_event(
                task=task,
                agent="Redis",
                action=f"hydrating memories for session {task.id}",
                metadata={"query": task.intent[:50], "status": "RUN"},
            )
        )
        await asyncio.sleep(0.6)

        events.append(
            await self._emit_event(
                task=task,
                agent="Context",
                action="querying svc_auth ground truth",
                metadata={"entity_type": "service", "status": "RUN"},
            )
        )
        await asyncio.sleep(0.55)

        # Hydrate memory + ground truth in parallel
        memories, service = await asyncio.gather(
            self.redis.hydrate(query=task.intent, session_id=task.id),
            self.context.query_entity("service", "svc_auth"),
        )

        # Preserve any operator_feedback already in the bundle
        preserved_feedback = task.context_bundle.get("operator_feedback")
        task.memory_provenance = [
            MemoryProvenance(
                text=m["text"],
                confidence=m["confidence"],
                source=m["source"],
            )
            for m in memories
        ]
        task.context_bundle = {"service": service, "memories_retrieved": len(memories)}
        if preserved_feedback:
            task.context_bundle["operator_feedback"] = preserved_feedback

        events.append(
            await self._emit_event(
                task=task,
                agent="Opus 4.6",
                action=f"sketching architecture against {service['name']}",
                metadata={
                    "memory_count": len(memories),
                    "service": service["name"],
                    "status": "PASS",
                },
            )
        )
        await asyncio.sleep(0.7)

        scaffolded = (
            "auth/middleware.py, tests/auth/"
            if task.type.value == "code"
            else "drafts/postmortem-TKT-002.md"
        )
        events.append(
            await self._emit_event(
                task=task,
                agent="Codex",
                action=f"scaffolding → {scaffolded}",
                metadata={"files": scaffolded, "status": "PASS"},
            )
        )
        await asyncio.sleep(0.7)

        events.append(
            await self._emit_event(
                task=task,
                agent="Gemini",
                action="reviewing sketch for consistency",
                metadata={
                    "verdict": "approved",
                    "status": "PASS",
                },
            )
        )

        # Stream the link out on the final event so the card can open
        # the full design markdown.
        events[-1].artifacts.append(render_and_save(task, "design"))
        await asyncio.sleep(0.55)

        return events
