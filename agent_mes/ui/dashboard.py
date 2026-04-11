"""Live dashboard — subscribes to pipeline events and updates the kanban
in real time. Uses rich.live.Live with a 10/s refresh rate.

When a stage event fires, the dashboard re-renders all 7 columns by
grouping tasks by current_stage and calling render_column on each.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from datetime import datetime

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from agent_mes.pipeline import Pipeline
from agent_mes.schema import MESTask, StageEnum, StageEvent
from agent_mes.ui.lanes import STAGES, build_layout, render_column


def _build_header(state: str = "ready") -> Panel:
    """Header that changes label based on pipeline state.

    state ∈ {'ready', 'running', 'complete'}
    """
    state_label = {
        "ready": ("press [enter] to launch", "bold yellow"),
        "running": ("pipeline running...", "bold blue"),
        "complete": ("complete — both tickets merged ✓", "bold green"),
    }[state]
    text = Text.assemble(
        ("AgentMES", "bold cyan"),
        " — manufacturing execution for autonomous agents — ",
        state_label,
        " — ",
        (datetime.now().strftime("%H:%M:%S"), "dim"),
    )
    return Panel(Align.center(text), border_style="cyan", padding=(0, 1))


class Dashboard:
    """Wraps a Live render loop around a Pipeline.run_parallel call."""

    def __init__(self, tasks: list[MESTask]) -> None:
        self.tasks = tasks
        self.layout = build_layout()
        self._lock = asyncio.Lock()
        self._state = "ready"
        # Initial render
        self._render_all()
        self._size_warned = False

    def _check_terminal_size(self) -> None:
        if self._size_warned:
            return
        size = shutil.get_terminal_size((80, 24))
        if size.columns < 180 or size.lines < 50:
            self._size_warned = True
            print(
                f"\n⚠ Terminal is {size.columns}x{size.lines}; "
                f"AgentMES kanban needs at least 180x50 for the cards to render without "
                f"aggressive line-wrapping. Resize your terminal (or zoom out a bit) before "
                f"running the demo.\n"
            )

    def _render_all(self) -> None:
        self.layout["header"].update(_build_header(self._state))
        # Group tasks by current_stage
        by_stage: dict[StageEnum, list[MESTask]] = {s: [] for s in StageEnum}
        for task in self.tasks:
            by_stage[task.current_stage].append(task)
        for stage in StageEnum:
            self.layout["board"][stage.value].update(render_column(by_stage[stage]))

    async def on_event(self, event: StageEvent, task: MESTask) -> None:
        async with self._lock:
            self._render_all()

    async def _await_launch_keypress(self) -> None:
        """Block until the user presses [enter]. Skipped when
        AGENTMES_AUTO_APPROVE=1 is set (rehearsal/test mode).
        """
        if os.environ.get("AGENTMES_AUTO_APPROVE") == "1":
            await asyncio.sleep(0.2)
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, input, "")

    async def run(self, pipeline: Pipeline) -> list[MESTask]:
        self._check_terminal_size()
        pipeline.events_callback = self.on_event

        with Live(self.layout, refresh_per_second=10, console=Console(), screen=False):
            # Initial state: cards in PLAN column with raw_input visible,
            # header says "press [enter] to launch"
            self._state = "ready"
            self._render_all()
            await self._await_launch_keypress()

            # Pipeline launch
            self._state = "running"
            self._render_all()
            results = await pipeline.run_parallel(self.tasks)

            # Final state
            self._state = "complete"
            await asyncio.sleep(0.5)
            self._render_all()
        return results
