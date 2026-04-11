"""BaseStage — common interface for all 7 AgentMES stages.

Each stage takes a MESTask, executes its work, emits one or more
StageEvents (the receipts that show up inside the card body), and
advances the task's current_stage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent_mes.schema import Artifact, MESTask, StageEnum, StageEvent


class BaseStage(ABC):
    """Abstract base class for the 7 stage classes."""

    STAGE: StageEnum  # subclass overrides
    AGENT: str = ""  # subclass overrides — primary agent label

    @abstractmethod
    async def execute(self, task: MESTask) -> list[StageEvent]:
        """Run the stage's work and return one or more StageEvents.

        Subclasses MUST append the events to task.events themselves AND
        return them so the pipeline can fan-out to the dashboard callback.
        """
        ...

    def _emit_event(
        self,
        task: MESTask,
        agent: str,
        action: str,
        metadata: dict[str, Any] | None = None,
        artifacts: list[Artifact] | None = None,
    ) -> StageEvent:
        """Helper — build a StageEvent for this stage and append to task.events."""
        event = StageEvent(
            stage=self.STAGE,
            agent=agent,
            action=action,
            metadata=metadata or {},
            artifacts=artifacts or [],
        )
        task.events.append(event)
        return event

    def _branch_by_type(self, task: MESTask) -> str:
        """Return 'simple' or 'code' so subclasses can switch behavior."""
        return task.type.value
