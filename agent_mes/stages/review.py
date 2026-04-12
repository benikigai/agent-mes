"""Stage 5 — Review. Cross-check every memory_provenance entry against
ground truth (Context Retriever). Catches the memory drift on TKT-001.
Emits a HumanGate (real input() unless AGENTMES_AUTO_APPROVE=1).
"""

from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable

from agent_mes.artifacts import render_and_save
from agent_mes.interfaces import ContextRetrieverProtocol, RedisMemoryProtocol
from agent_mes.schema import Artifact, HumanGate, MESTask, StageEnum, StageEvent, TicketType
from agent_mes.stages.base import BaseStage

# Type alias for the optional browser-driven gate hook.
# Receives the HumanGate, returns True on approval / False on rejection or timeout.
GateProvider = Callable[[HumanGate], Awaitable[bool]]


class ReviewStage(BaseStage):
    STAGE = StageEnum.REVIEW
    AGENT = "Opus 4.6"

    def __init__(
        self,
        redis: RedisMemoryProtocol,
        context: ContextRetrieverProtocol,
        gate_provider: GateProvider | None = None,
    ) -> None:
        self.redis = redis
        self.context = context
        self.gate_provider = gate_provider

    async def execute(self, task: MESTask) -> list[StageEvent]:
        task.current_stage = StageEnum.REVIEW
        events: list[StageEvent] = []
        drift_caught = False

        events.append(
            await self._emit_event(
                task=task,
                agent="Opus 4.6",
                action=f"first-pass review: {len(task.memory_provenance)} memories to verify",
                metadata={"memories": len(task.memory_provenance), "status": "RUN"},
            )
        )
        await asyncio.sleep(0.75)

        events.append(
            await self._emit_event(
                task=task,
                agent="Context",
                action="cross-checking memory claims against incident ground truth",
                metadata={"entity_type": "incident", "status": "RUN"},
            )
        )
        await asyncio.sleep(0.75)

        # Both CODE and SIMPLE tickets run memory verification — drift catches
        # fire whenever a hydrated memory contradicts a Context Surfaces fact.
        for memory in task.memory_provenance:
            verification = await self.context.verify_claim(
                claim=memory.text,
                entity_type="incident",
            )
            if not verification["verified"]:
                drift_caught = True
                memory.confidence = round(max(0.3, memory.confidence - 0.6), 2)
                # Pull the plushpalace source link from the verify_claim
                # `actual` payload so the drift event carries a clickable
                # link back to the real YAML record it contradicted.
                actual = verification.get("actual", {}) or {}
                drift_artifacts = []
                pp_gh = actual.get("plushpalace_github")
                pp_yaml = actual.get("plushpalace_yaml")
                if pp_gh:
                    drift_artifacts.append(
                        Artifact(
                            type="file",
                            ref=pp_gh,
                            summary=f"↗ ground truth: {pp_yaml or 'data/'} · {actual.get('incident_id', '?')}",
                        )
                    )
                events.append(
                    await self._emit_event(
                        task=task,
                        agent="Opus 4.6",
                        action=f"memory drift: {verification['discrepancy'][:50]}",
                        metadata={
                            "prior_incident": actual.get("incident_id", "unknown"),
                            "discrepancy": verification["discrepancy"][:80],
                            "confidence_after": memory.confidence,
                            "status": "DRIFT",
                        },
                        artifacts=drift_artifacts,
                    )
                )
                await asyncio.sleep(0.55)

        if drift_caught:
            # The HumanGate — pause for browser Approve click or stdin input.
            task.status = "blocked"
            gate = HumanGate(
                stage=StageEnum.REVIEW,
                prompt="memory drift caught — approve corrected fix? [y/n] ",
            )
            events.append(
                await self._emit_event(
                    task=task,
                    agent="HUMAN",
                    action="awaiting approval",
                    metadata={"prompt": gate.prompt, "status": "RUN"},
                )
            )

            approved = await self._await_human(gate)
            gate.approved = approved
            gate.approver = "ben" if approved else None
            task.human_gates.append(gate)
            task.status = "running"

            events.append(
                await self._emit_event(
                    task=task,
                    agent="HUMAN",
                    action="approved" if approved else "rejected",
                    metadata={
                        "approver": gate.approver or "none",
                        "status": "PASS" if approved else "FAIL",
                    },
                )
            )
        else:
            # Auto-approve when no drift OR for SIMPLE tickets
            events.append(
                await self._emit_event(
                    task=task,
                    agent="Opus 4.6",
                    action="reviewed — matches intent, no drift",
                    metadata={"status": "PASS"},
                )
            )

        events[-1].artifacts.append(render_and_save(task, "review"))
        await asyncio.sleep(0.6)
        return events

    async def _await_human(self, gate: HumanGate) -> bool:
        """Three modes, in priority order:
        1. If gate_provider is set (web mode), call it and return its result
        2. If AGENTMES_AUTO_APPROVE=1 env var is set, auto-approve (test mode)
        3. Otherwise, prompt for keyboard input via stdin (terminal mode)
        """
        if self.gate_provider is not None:
            return await self.gate_provider(gate)
        if os.environ.get("AGENTMES_AUTO_APPROVE") == "1":
            await asyncio.sleep(0.1)
            return True
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, input, gate.prompt)
        return response.strip().lower() in ("y", "yes")
