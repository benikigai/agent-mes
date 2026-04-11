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

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from agent_mes.schema import Artifact, MESTask, StageEnum, StageEvent

if TYPE_CHECKING:
    from agent_mes.pipeline import Pipeline


class BaseStage(ABC):
    """Abstract base class for the 7 stage classes."""

    STAGE: StageEnum  # subclass overrides
    AGENT: str = ""  # subclass overrides — primary agent label

    # Set by Pipeline.__init__ so _emit_event can stream events live.
    _pipeline: "Pipeline | None" = None

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

    def _branch_by_type(self, task: MESTask) -> str:
        """Return 'simple' or 'code' so subclasses can switch behavior."""
        return task.type.value
