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
from agent_mes.artifacts import render_and_save
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

        events: list[StageEvent] = []

        # 0. Re-plan path — if operator sent feedback on a prior run, show
        # it going into the new plan so the loop is visible.
        feedback_history: list[str] = task.context_bundle.get("operator_feedback", [])
        if feedback_history:
            events.append(
                await self._emit_event(
                    task=task,
                    agent="HUMAN",
                    action=f"incorporating feedback #{len(feedback_history)}",
                    metadata={
                        "feedback": feedback_history[-1][:80],
                        "total_feedback": len(feedback_history),
                        "status": "RUN",
                    },
                )
            )
            await asyncio.sleep(0.6)

        # 1. Parse the raw Slack message — Opus 4.6 extracts intent + ACs
        events.append(
            await self._emit_event(
                task=task,
                agent=self.AGENT,
                action="parsing raw Slack message",
                metadata={"channel": task.source, "chars": len(task.raw_input), "status": "RUN"},
            )
        )
        await asyncio.sleep(0.7)

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

        events.append(
            await self._emit_event(
                task=task,
                agent=self.AGENT,
                action=f"extracted intent: {task.intent[:50]}",
                metadata={
                    "intent_chars": len(task.intent),
                    "ac_count": len(task.acceptance_criteria),
                    "status": "PASS",
                },
            )
        )
        await asyncio.sleep(0.6)

        # 2. Classify ticket type — SIMPLE keywords win because postmortems
        # often mention "deploy" or "fix" in their bodies.
        text_lower = task.raw_input.lower()
        if any(k in text_lower for k in SIMPLE_KEYWORDS):
            task.type = TicketType.SIMPLE
        elif any(k in text_lower for k in CODE_KEYWORDS):
            task.type = TicketType.CODE
        else:
            task.type = TicketType.SIMPLE

        events.append(
            await self._emit_event(
                task=task,
                agent=self.AGENT,
                action=f"classified={task.type.value}, {len(task.acceptance_criteria)} ACs",
                metadata={
                    "type": task.type.value,
                    "ac_count": len(task.acceptance_criteria),
                    "blast_radius": (
                        "isolated" if not task.blast_radius.network_egress else "egress_ok"
                    ),
                    "status": "PASS",
                },
            )
        )
        await asyncio.sleep(0.55)

        # 3. Auto-approving HumanGate — this is the bipartite-rubric
        # "engineers own" column for Plan, wired as an auto-approve gate
        # for the demo.
        gate = HumanGate(
            stage=StageEnum.PLAN,
            prompt=f"Approve plan for {task.id}?",
            approved=True,
            approver="auto",
        )
        task.human_gates.append(gate)
        events.append(
            await self._emit_event(
                task=task,
                agent="HUMAN",
                action="plan auto-approved",
                metadata={"approver": "auto", "status": "PASS"},
            )
        )

        # Attach the "open stage output" link to the final event so the
        # card can link out to the plan markdown.
        events[-1].artifacts.append(render_and_save(task, "plan"))
        await asyncio.sleep(0.55)

        return events
