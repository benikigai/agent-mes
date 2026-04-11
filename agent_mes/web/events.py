"""SSE event broker — fans out pipeline StageEvents to all browser clients.

Each subscriber gets its own asyncio.Queue so a slow client can't block
the others. publish() serializes the StageEvent + a snapshot of the task
into a JSON-friendly dict and pushes it onto every subscriber's queue.
"""

from __future__ import annotations

import asyncio
from typing import Any

from agent_mes.schema import MESTask, StageEvent


def _task_payload(task: MESTask) -> dict[str, Any]:
    """Serialize a task for the SSE wire — includes the full event history
    so a refresh-rehydrating client doesn't need a separate fetch."""
    return {
        "id": task.id,
        "type": task.type.value,
        "intent": task.intent,
        "raw_input": task.raw_input,
        "requester": task.requester,
        "source": task.source,
        "current_stage": task.current_stage.value,
        "status": task.status,
        "events": [e.model_dump(mode="json") for e in task.events],
    }


def _event_payload(event: StageEvent, task: MESTask) -> dict[str, Any]:
    return {
        "type": "event",
        "task_id": task.id,
        "event": event.model_dump(mode="json"),
        "task": _task_payload(task),
    }


def _state_payload(tasks: list[MESTask]) -> dict[str, Any]:
    return {
        "type": "state",
        "tasks": [_task_payload(t) for t in tasks],
    }


class EventBroker:
    """Per-client asyncio.Queue subscriber broker."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def publish(self, event: StageEvent, task: MESTask) -> None:
        """Pipeline events_callback hook — fans out to all subscribers."""
        payload = _event_payload(event, task)
        for q in list(self._subscribers):
            await q.put(payload)

    def current_state(self, tasks: list[MESTask]) -> dict[str, Any]:
        """Snapshot helper — used to push initial state on new connections."""
        return _state_payload(tasks)
