"""Rich Layout for the 7-column vertical kanban + detailed-changelog cards.

The card body is a running detailed changelog: title, intent, separator,
then for each StageEnum that has events: a stage header (cyan bold),
followed by event lines with symbols, indented metadata, and indented
artifact references. Cards grow as task.events grows.
"""

from __future__ import annotations

from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from agent_mes.schema import MESTask, StageEnum

STAGES = [s.value for s in StageEnum]  # ['plan','design','build','test','review','document','deploy']

SYMBOLS = {
    "PASS": "✓",
    "FAIL": "✗",
    "KILLED": "✗",
    "DRIFT": "⚠",
    "WARN": "⚠",
    "RUN": "⏳",
}

INTERNAL_META_KEYS = {"status", "ticket_id"}

BORDER_BY_STATUS = {
    "merged": "green",
    "running": "blue",
    "blocked": "yellow",
    "killed": "red",
    "pending": "dim",
}


def build_layout() -> Layout:
    """Build the root Layout: 3-row header + 7-column board."""
    root = Layout(name="root")
    root.split_column(
        Layout(name="header", size=3),
        Layout(name="board"),
    )
    root["board"].split_row(*[Layout(name=stage) for stage in STAGES])
    return root


def render_card(task: MESTask) -> Panel:
    """Render a single task as a Panel containing the running changelog."""
    type_icon = "⚙" if task.type.value == "code" else "✉"
    title = f"{type_icon} {task.id}"

    lines: list[Text] = [
        Text(task.intent[:34], style="bold white"),
        Text("─" * 32, style="dim"),
    ]

    # Group events by stage so we can render section headers
    by_stage: dict[StageEnum, list] = {}
    for event in task.events:
        by_stage.setdefault(event.stage, []).append(event)

    for stage in StageEnum:
        if stage not in by_stage:
            continue
        lines.append(Text(f"━ {stage.value.upper()} ━", style="bold cyan"))
        for event in by_stage[stage]:
            symbol = SYMBOLS.get(event.metadata.get("status", "PASS"), "•")
            agent_short = event.agent.split()[0]
            lines.append(Text(f"{symbol} [{agent_short}] {event.action[:34]}"))
            for key, val in event.metadata.items():
                if key in INTERNAL_META_KEYS:
                    continue
                val_short = str(val)[:28]
                lines.append(Text(f"   {key}: {val_short}", style="dim"))
            for artifact in event.artifacts:
                ref_short = artifact.ref[:28]
                lines.append(Text(f"   → {artifact.type}: {ref_short}", style="green"))

    border = BORDER_BY_STATUS.get(task.status, "white")
    return Panel(Group(*lines), title=title, border_style=border, padding=(0, 1))


def render_column(tasks_in_col: list[MESTask]) -> Panel:
    """Render a column as a stack of card Panels (with the column name as title)."""
    if not tasks_in_col:
        return Panel("", border_style="dim")
    cards = [render_card(t) for t in tasks_in_col]
    return Panel(Group(*cards), border_style="dim", padding=(0, 0))
