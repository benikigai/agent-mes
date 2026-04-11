"""Stage 1 — Plan. Convert raw input → MESTask first-stage payload via Wordware,
classify ticket type via heuristic, record auto-approving HumanGate.
"""

from __future__ import annotations

import asyncio

from agent_mes.interfaces import WordwarePlannerProtocol
from agent_mes.schema import (
    AcceptanceCriterion,
    BlastRadius,
    HumanGate,
    MESTask,
    StageEnum,
    StageEvent,
    TicketType,
)
from agent_mes.stages.base import BaseStage

SIMPLE_KEYWORDS = {"draft", "postmortem", "email", "summary", "report", "write up", "write a", "send", "notify"}
CODE_KEYWORDS = {"fix", "implement", "refactor", "bug", "patch", "rate limit", "oauth", "race condition", "test_", "flaky"}


class PlanStage(BaseStage):
    STAGE = StageEnum.PLAN
    AGENT = "Opus 4.6"

    def __init__(self, wordware: WordwarePlannerProtocol) -> None:
        self.wordware = wordware

    async def execute(self, task: MESTask) -> list[StageEvent]:
        task.current_stage = StageEnum.PLAN
        task.status = "running"

        plan_payload = await self.wordware.plan_from_slack(
            raw_text=task.raw_input,
            requester=task.requester,
            channel=task.source,
        )

        task.intent = plan_payload.get("intent", task.intent or task.raw_input)
        task.acceptance_criteria = [
            AcceptanceCriterion(**ac) for ac in plan_payload.get("acceptance_criteria", [])
        ]
        if "blast_radius" in plan_payload:
            task.blast_radius = BlastRadius(**plan_payload["blast_radius"])

        # Classify ticket type via keyword heuristic — SIMPLE keywords win
        # because postmortems often mention "deploy" or "fix" in their bodies.
        text_lower = task.raw_input.lower()
        if any(k in text_lower for k in SIMPLE_KEYWORDS):
            task.type = TicketType.SIMPLE
        elif any(k in text_lower for k in CODE_KEYWORDS):
            task.type = TicketType.CODE
        else:
            task.type = TicketType.SIMPLE

        event = self._emit_event(
            task=task,
            agent=self.AGENT,
            action=f"classified={task.type.value}",
            metadata={
                "ac_count": len(task.acceptance_criteria),
                "blast_radius": "isolated" if not task.blast_radius.network_egress else "egress_ok",
                "status": "PASS",
            },
        )

        # Auto-approving HumanGate (2 second pause for visual effect)
        gate = HumanGate(
            stage=StageEnum.PLAN,
            prompt=f"Approve plan for {task.id}?",
            approved=True,
            approver="auto",
        )
        task.human_gates.append(gate)
        await asyncio.sleep(0.2)  # condensed for fast demo runs

        return [event]
