"""Stage 5 — Review. Cross-check every memory_provenance entry against
ground truth (Context Retriever). Catches the memory drift on TKT-001.
Emits a HumanGate (real input() unless AGENTMES_AUTO_APPROVE=1).
"""

from __future__ import annotations

import asyncio

from agent_mes.artifacts import render_and_save
from agent_mes.interfaces import (
    ContextRetrieverProtocol,
    HumanGateProvider,
    RedisMemoryProtocol,
)
from agent_mes.schema import (
    Artifact,
    GateDecision,
    HumanGate,
    MESTask,
    StageEnum,
    StageEvent,
)
from agent_mes.stages.base import BaseStage


class ReviewStage(BaseStage):
    STAGE = StageEnum.REVIEW
    AGENT = "Opus 4.6"

    def __init__(
        self,
        redis: RedisMemoryProtocol,
        context: ContextRetrieverProtocol,
        gate_provider: HumanGateProvider | None = None,
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

            decision = await self._await_human(gate)
            approved = decision == GateDecision.APPROVED
            gate.approved = approved
            gate.approver = "ben" if approved else None
            task.human_gates.append(gate)

            if not approved:
                # A rejected or expired review HALTS the pipeline — the ticket
                # does NOT proceed to Document/Deploy and never merges. (This
                # was the no-op bug: the old code set status="running" here and
                # the rejected fix sailed through to merged.) A reject-with-
                # feedback re-plan is a different path — /api/feedback cancels
                # and rebuilds the task instead of resolving this gate.
                terminal = "rejected" if decision == GateDecision.REJECTED else "expired"
                events.append(
                    await self._emit_event(
                        task=task,
                        agent="HUMAN",
                        action=(
                            "rejected — fix not approved, ticket closed"
                            if decision == GateDecision.REJECTED
                            else "review gate expired — no decision, ticket closed"
                        ),
                        metadata={"status": "FAIL", "decision": decision.value},
                    )
                )
                events[-1].artifacts.append(render_and_save(task, "review"))
                task.status = terminal
                return events

            task.status = "running"
            events.append(
                await self._emit_event(
                    task=task,
                    agent="HUMAN",
                    action="approved",
                    metadata={"approver": gate.approver, "status": "PASS"},
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
