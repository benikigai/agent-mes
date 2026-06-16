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


# Public deployment caps. The broker is a fan-out amplifier on a single
# uvicorn worker behind a Cloudflare tunnel, so both dimensions are bounded:
#   MAX_SUBSCRIBERS — refuse new SSE connections past this (the route 503s),
#                     bounding connection-exhaustion floods.
#   QUEUE_MAXSIZE   — per-client buffer; a full run is ~30-60 events, so this
#                     is a generous burst margin. On overflow we drop the
#                     OLDEST event for that client (a refresh re-hydrates full
#                     state anyway) rather than blocking the publish loop —
#                     one slow client can never back-pressure the pipeline or
#                     grow memory without bound.
MAX_SUBSCRIBERS = 50  # global ceiling — bounds total memory/connections
MAX_SUBSCRIBERS_PER_KEY = 5  # per-visitor ceiling — one client can't 503 everyone
QUEUE_MAXSIZE = 256


class SubscriberLimitExceeded(Exception):
    """Raised by subscribe() when the global or per-visitor cap is reached."""


class EventBroker:
    """Per-client asyncio.Queue subscriber broker."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        self._key_of: dict[asyncio.Queue[dict[str, Any]], str] = {}
        self._per_key: dict[str, int] = {}

    def subscribe(self, key: str = "anon") -> asyncio.Queue[dict[str, Any]]:
        if len(self._subscribers) >= MAX_SUBSCRIBERS:
            raise SubscriberLimitExceeded(
                f"at capacity ({MAX_SUBSCRIBERS} live connections)"
            )
        if self._per_key.get(key, 0) >= MAX_SUBSCRIBERS_PER_KEY:
            raise SubscriberLimitExceeded(
                f"too many connections from one visitor (max {MAX_SUBSCRIBERS_PER_KEY})"
            )
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._subscribers.append(q)
        self._key_of[q] = key
        self._per_key[key] = self._per_key.get(key, 0) + 1
        return q

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)
        key = self._key_of.pop(queue, None)
        if key is not None:
            remaining = self._per_key.get(key, 0) - 1
            if remaining <= 0:
                self._per_key.pop(key, None)
            else:
                self._per_key[key] = remaining

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def _fanout(self, payload: dict[str, Any]) -> None:
        """Push to every subscriber without blocking. On a full queue, drop
        the oldest buffered item for that client and enqueue the newest — a
        bounded ring buffer, so a slow consumer loses stale events but never
        stalls the publisher or grows memory."""
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

    async def publish(self, event: StageEvent, task: MESTask) -> None:
        """Pipeline events_callback hook — fans out to all subscribers."""
        self._fanout(_event_payload(event, task))

    def broadcast(self, payload: dict[str, Any]) -> None:
        """Fan out a pre-built payload (e.g. a state snapshot) to subscribers."""
        self._fanout(payload)

    def current_state(self, tasks: list[MESTask]) -> dict[str, Any]:
        """Snapshot helper — used to push initial state on new connections."""
        return _state_payload(tasks)
