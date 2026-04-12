"""Stage 2 — Design. Hydrate context_bundle (Context Retriever) and
memory_provenance (Redis Memory) in parallel. Emits THREE StageEvents
representing the Opus + Codex + Gemini sub-agents.
"""

from __future__ import annotations

import asyncio

from agent_mes.artifacts import render_and_save
from agent_mes.interfaces import ContextRetrieverProtocol, RedisMemoryProtocol
from agent_mes.schema import Artifact, MemoryProvenance, MESTask, StageEnum, StageEvent
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
        # Preserve the raw hydrated memory dicts so downstream stages (Review)
        # can access the plushpalace source fields that MemoryProvenance drops
        task.context_bundle["hydrated_memories_raw"] = memories
        if preserved_feedback:
            task.context_bundle["operator_feedback"] = preserved_feedback

        # Surface every hydrated memory as a clickable plushpalace-world
        # GitHub link so the card's Design lane proves the Redis call
        # actually returned real data from a real source.
        hydration_artifacts = [
            Artifact(
                type="memory",
                ref=m.get("plushpalace_github")
                or f"https://github.com/benikigai/plushpalace-world/blob/main/{m.get('plushpalace_yaml','data/')}",
                summary=f"↗ {m.get('plushpalace_yaml','data/')} · {m.get('source','?')}",
            )
            for m in memories
            if m.get("plushpalace_github") or m.get("plushpalace_yaml")
        ]
        events.append(
            await self._emit_event(
                task=task,
                agent="Redis",
                action=f"hydrated {len(memories)} records from plushpalace-world",
                metadata={
                    "count": len(memories),
                    "sources": [m.get("source", "?") for m in memories],
                    "top_confidence": max((m.get("confidence", 0) for m in memories), default=0),
                    "status": "PASS",
                },
                artifacts=hydration_artifacts,
            )
        )
        await asyncio.sleep(0.55)

        # Same for Context Surfaces — show the entity query hit and where
        # the ground-truth data came from on GitHub.
        ctx_artifacts = []
        pp_yaml = service.get("plushpalace_yaml") if isinstance(service, dict) else None
        pp_gh = service.get("plushpalace_github") if isinstance(service, dict) else None
        if pp_gh:
            ctx_artifacts.append(
                Artifact(
                    type="file",
                    ref=pp_gh,
                    summary=f"↗ {pp_yaml or 'data/'} · svc_auth ground truth",
                )
            )
        events.append(
            await self._emit_event(
                task=task,
                agent="Context",
                action=f"retrieved entity: {service.get('name', 'svc_auth')}",
                metadata={
                    "entity": service.get("name", "svc_auth"),
                    "fields": [
                        k for k in list(service.keys())[:6] if not k.startswith("plushpalace_")
                    ],
                    "status": "PASS",
                },
                artifacts=ctx_artifacts,
            )
        )
        await asyncio.sleep(0.55)

        events.append(
            await self._emit_event(
                task=task,
                agent="Opus 4.6",
                action=f"sketching architecture against {service.get('name', 'svc_auth')}",
                metadata={
                    "memory_count": len(memories),
                    "service": service.get("name", "svc_auth"),
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
