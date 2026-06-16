"""Per-task asyncio.Event registry — backs the ReviewStage gate_provider.

The browser POSTs /api/approve/{task_id} which calls approve(). The
ReviewStage awaits the same task_id via wait(). Order-independent: if
approve fires before wait, wait returns immediately because the event
is already set.
"""

from __future__ import annotations

import asyncio

from agent_mes.schema import GateDecision


class GateRegistry:
    """Per-task asyncio.Event registry for browser-driven HumanGate decisions.

    The browser POSTs /api/approve or /api/reject; the gated stage awaits the
    same key via wait(), which returns the GateDecision the operator made (or
    TIMED_OUT). Order-independent: a decision recorded before the stage starts
    waiting is still delivered to the later wait()."""

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._decisions: dict[str, GateDecision] = {}

    def register(self, task_id: str) -> asyncio.Event:
        """Get or create the event for this task. Idempotent."""
        if task_id not in self._events:
            self._events[task_id] = asyncio.Event()
        return self._events[task_id]

    def resolve(self, task_id: str, decision: GateDecision) -> None:
        """Record a human decision and unblock any waiter. Order-independent —
        if no waiter is registered yet, this still creates and sets the event so
        a later wait() returns the decision immediately."""
        self._decisions[task_id] = decision
        self.register(task_id).set()

    def approve(self, task_id: str) -> None:
        """Convenience: resolve the gate as APPROVED."""
        self.resolve(task_id, GateDecision.APPROVED)

    def reject(self, task_id: str) -> None:
        """Convenience: resolve the gate as REJECTED."""
        self.resolve(task_id, GateDecision.REJECTED)

    async def wait(self, task_id: str, timeout: float = 300.0) -> GateDecision:
        """Block until the gate is resolved for this task_id, or timeout.
        Returns the recorded GateDecision on resolution, TIMED_OUT on timeout."""
        event = self.register(task_id)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._decisions.get(task_id, GateDecision.APPROVED)
        except asyncio.TimeoutError:
            return GateDecision.TIMED_OUT

    def reset(self) -> None:
        """Clear all events. Called on /api/launch to start a fresh run."""
        self._events.clear()
        self._decisions.clear()

    def reset_task(self, task_id: str) -> None:
        """Clear every gate event tied to a task — handles both the legacy
        bare ``task_id`` key and the namespaced ``task_id:stage`` variants
        that Review and Deploy use."""
        prefix = f"{task_id}:"
        for key in list(self._events.keys()):
            if key == task_id or key.startswith(prefix):
                self._events.pop(key, None)
                self._decisions.pop(key, None)

    @property
    def pending(self) -> list[str]:
        """Task ids that have a registered but unset event (i.e. waiting)."""
        return [tid for tid, ev in self._events.items() if not ev.is_set()]
