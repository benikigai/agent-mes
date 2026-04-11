"""Per-task asyncio.Event registry — backs the ReviewStage gate_provider.

The browser POSTs /api/approve/{task_id} which calls approve(). The
ReviewStage awaits the same task_id via wait(). Order-independent: if
approve fires before wait, wait returns immediately because the event
is already set.
"""

from __future__ import annotations

import asyncio


class GateRegistry:
    """Per-task asyncio.Event registry for browser-driven HumanGate approvals."""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}

    def register(self, task_id: str) -> asyncio.Event:
        """Get or create the event for this task. Idempotent."""
        if task_id not in self._events:
            self._events[task_id] = asyncio.Event()
        return self._events[task_id]

    def approve(self, task_id: str) -> None:
        """Set the event so any waiter unblocks. Order-independent — if no
        waiter is registered yet, this still creates and sets the event so
        a later wait() call returns immediately."""
        event = self.register(task_id)
        event.set()

    async def wait(self, task_id: str, timeout: float = 300.0) -> bool:
        """Block until approve() fires for this task_id, or timeout. Returns
        True on approval, False on timeout."""
        event = self.register(task_id)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def reset(self) -> None:
        """Clear all events. Called on /api/launch to start a fresh run."""
        self._events.clear()

    def reset_task(self, task_id: str) -> None:
        """Clear every gate event tied to a task — handles both the legacy
        bare ``task_id`` key and the namespaced ``task_id:stage`` variants
        that Review and Deploy use."""
        prefix = f"{task_id}:"
        for key in list(self._events.keys()):
            if key == task_id or key.startswith(prefix):
                self._events.pop(key, None)

    @property
    def pending(self) -> list[str]:
        """Task ids that have a registered but unset event (i.e. waiting)."""
        return [tid for tid, ev in self._events.items() if not ev.is_set()]
