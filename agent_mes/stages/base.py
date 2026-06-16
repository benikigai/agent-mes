"""BaseStage — common interface for all 7 AgentMES stages.

Each stage takes a MESTask, executes its work, emits one or more
StageEvents (the receipts that show up inside the card body), and
advances the task's current_stage.

``_emit_event`` is async and fires the event through the owning
Pipeline's ``events_callback`` immediately — so the browser sees each
event land the moment it happens inside the stage, instead of having
to wait for ``execute()`` to return. This is what keeps the live
kanban flowing while ReviewStage is blocked on a human gate.
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from agent_mes.schema import (
    Artifact,
    GateDecision,
    HumanGate,
    MESTask,
    StageEnum,
    StageEvent,
)

if TYPE_CHECKING:
    from agent_mes.interfaces import HumanGateProvider
    from agent_mes.pipeline import Pipeline


class BaseStage(ABC):
    """Abstract base class for the 7 stage classes."""

    STAGE: StageEnum  # subclass overrides
    AGENT: str = ""  # subclass overrides — primary agent label

    # Set by Pipeline.__init__ so _emit_event can stream events live.
    _pipeline: "Pipeline | None" = None

    # Set by the gated stages (Review, Deploy) in __init__. None in terminal/
    # headless mode, where _await_human falls back to AGENTMES_AUTO_APPROVE or
    # stdin. Declared here so the shared _await_human works for any stage.
    gate_provider: "HumanGateProvider | None" = None

    @abstractmethod
    async def execute(self, task: MESTask) -> list[StageEvent]:
        """Run the stage's work.

        Subclasses MUST use ``await self._emit_event(...)`` (not the
        sync constructor) so each event streams out live. They may
        return the list of emitted events for tests; the pipeline no
        longer re-fires whatever ``execute()`` returns.
        """
        ...

    async def _emit_event(
        self,
        task: MESTask,
        agent: str,
        action: str,
        metadata: dict[str, Any] | None = None,
        artifacts: list[Artifact] | None = None,
    ) -> StageEvent:
        """Append a StageEvent to ``task.events`` **and** immediately fire
        the pipeline's events_callback so the browser renders it live."""
        event = StageEvent(
            stage=self.STAGE,
            agent=agent,
            action=action,
            metadata=metadata or {},
            artifacts=artifacts or [],
        )
        task.events.append(event)
        if self._pipeline is not None:
            await self._pipeline._fire(event, task)  # noqa: SLF001 — internal contract
        return event

    async def _await_human(self, gate: HumanGate) -> GateDecision:
        """Resolve a HumanGate, in priority order:
        1. gate_provider set (web mode) — await the browser's approve/reject.
        2. AGENTMES_AUTO_APPROVE=1 (test/rehearsal mode) — auto-approve.
        3. stdin prompt (terminal mode) — y/yes approves, anything else rejects.

        Shared by ReviewStage and DeployStage so the two human gates resolve
        through one code path (replaces the two duplicate copies that used to
        return a bool and conflate reject with timeout).
        """
        if self.gate_provider is not None:
            return await self.gate_provider(gate)
        if os.environ.get("AGENTMES_AUTO_APPROVE") == "1":
            await asyncio.sleep(0.1)
            return GateDecision.APPROVED
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, input, gate.prompt)
        if response.strip().lower() in ("y", "yes"):
            return GateDecision.APPROVED
        return GateDecision.REJECTED

    def _branch_by_type(self, task: MESTask) -> str:
        """Return 'simple' or 'code' so subclasses can switch behavior."""
        return task.type.value
