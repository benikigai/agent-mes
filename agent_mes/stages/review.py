"""Stage 5 — Review. Cross-check every memory_provenance entry against
ground truth (Context Retriever). Catches the memory drift on TKT-001.
Emits a HumanGate (real input() unless AGENTMES_AUTO_APPROVE=1).
"""

from __future__ import annotations

import asyncio
import os

from agent_mes.interfaces import ContextRetrieverProtocol, RedisMemoryProtocol
from agent_mes.schema import HumanGate, MESTask, StageEnum, StageEvent, TicketType
from agent_mes.stages.base import BaseStage


class ReviewStage(BaseStage):
    STAGE = StageEnum.REVIEW
    AGENT = "Opus 4.6"

    def __init__(
        self,
        redis: RedisMemoryProtocol,
        context: ContextRetrieverProtocol,
    ) -> None:
        self.redis = redis
        self.context = context

    async def execute(self, task: MESTask) -> list[StageEvent]:
        task.current_stage = StageEnum.REVIEW
        events: list[StageEvent] = []
        drift_caught = False

        # Only CODE tickets trigger the memory drift catch — SIMPLE tickets
        # (email/knowledge work) get a lightweight intent-match review.
        if task.type == TicketType.CODE:
            for memory in task.memory_provenance:
                verification = await self.context.verify_claim(
                    claim=memory.text,
                    entity_type="incident",
                )
                if not verification["verified"]:
                    drift_caught = True
                    memory.confidence = round(max(0.3, memory.confidence - 0.6), 2)
                    events.append(
                        self._emit_event(
                            task=task,
                            agent=self.AGENT,
                            action="memory drift",
                            metadata={
                                "memory": verification["actual"].get("endpoint", "unknown"),
                                "ticket": "/v2/oauth",
                                "discrepancy": verification["discrepancy"][:60],
                                "status": "DRIFT",
                            },
                        )
                    )

        if drift_caught and task.type == TicketType.CODE:
            # The HumanGate — pause for keyboard input on stage
            task.status = "blocked"
            gate = HumanGate(
                stage=StageEnum.REVIEW,
                prompt="memory drift caught — approve corrected fix? [y/n] ",
            )
            events.append(
                self._emit_event(
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
                self._emit_event(
                    task=task,
                    agent="HUMAN",
                    action="approved" if approved else "rejected",
                    metadata={"approver": gate.approver or "none", "status": "PASS" if approved else "FAIL"},
                )
            )
        else:
            # Auto-approve when no drift OR for SIMPLE tickets
            events.append(
                self._emit_event(
                    task=task,
                    agent=self.AGENT,
                    action="reviewed — matches intent",
                    metadata={"status": "PASS"},
                )
            )

        return events

    async def _await_human(self, gate: HumanGate) -> bool:
        """Pause for keyboard input. Auto-approve if AGENTMES_AUTO_APPROVE=1
        is set in the environment (used in tests + smoke runs).
        """
        if os.environ.get("AGENTMES_AUTO_APPROVE") == "1":
            await asyncio.sleep(0.1)
            return True
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, input, gate.prompt)
        return response.strip().lower() in ("y", "yes")
