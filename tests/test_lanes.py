"""Tests for ui/lanes.py — layout structure + card rendering."""

from agent_mes.schema import (
    Artifact,
    MESTask,
    StageEnum,
    StageEvent,
    TicketType,
)
from agent_mes.ui.lanes import (
    STAGES,
    build_layout,
    render_card,
    render_column,
)


def test_build_layout_has_seven_columns():
    layout = build_layout()
    assert len(STAGES) == 7
    for stage in STAGES:
        # Accessing by name should not raise
        _ = layout["board"][stage]


def test_render_card_for_one_event_task():
    task = MESTask(
        id="TKT-001",
        type=TicketType.CODE,
        intent="raise the OAuth /v2 rate limit",
        raw_input="",
        requester="sarah",
        source="#bugs",
        events=[
            StageEvent(
                stage=StageEnum.PLAN,
                agent="Opus 4.6",
                action="classified=code",
                metadata={"ac_count": 3, "blast_radius": "isolated", "status": "PASS"},
            )
        ],
    )
    panel = render_card(task)
    assert panel.title.startswith("⚙ TKT-001")


def test_render_card_for_simple_uses_email_icon():
    task = MESTask(
        id="TKT-002",
        type=TicketType.SIMPLE,
        intent="draft email",
        raw_input="",
        requester="marcus",
        source="#announcements",
    )
    panel = render_card(task)
    assert panel.title.startswith("✉ TKT-002")


def test_render_card_with_full_history():
    """A task with events across all 7 stages should produce a tall card."""
    events = [
        StageEvent(stage=StageEnum.PLAN, agent="Opus 4.6", action="classified=code"),
        StageEvent(stage=StageEnum.DESIGN, agent="Opus 4.6", action="sketched"),
        StageEvent(stage=StageEnum.DESIGN, agent="Codex", action="scaffolded"),
        StageEvent(stage=StageEnum.DESIGN, agent="Gemini", action="reviewed"),
        StageEvent(
            stage=StageEnum.BUILD,
            agent="Codex",
            action="diff +47/-3",
            artifacts=[Artifact(type="file", ref="auth/middleware.py", summary="")],
        ),
        StageEvent(stage=StageEnum.TEST, agent="Gemini", action="iter 1: FAIL"),
        StageEvent(stage=StageEnum.TEST, agent="Blaxel", action="iter 2: KILLED",
                   metadata={"status": "KILLED"}),
        StageEvent(stage=StageEnum.TEST, agent="Gemini", action="iter 3: PASS"),
        StageEvent(stage=StageEnum.REVIEW, agent="Opus 4.6", action="memory drift",
                   metadata={"status": "DRIFT"}),
        StageEvent(stage=StageEnum.REVIEW, agent="HUMAN", action="approved"),
        StageEvent(stage=StageEnum.DOCUMENT, agent="Redis", action="lesson written: mem_4471"),
        StageEvent(stage=StageEnum.DEPLOY, agent="GitHub", action="PR opened"),
    ]
    task = MESTask(
        id="TKT-001",
        type=TicketType.CODE,
        intent="OAuth /v2 fix",
        raw_input="",
        requester="sarah",
        source="#bugs",
        events=events,
        status="merged",
    )
    panel = render_card(task)
    # Just confirm it doesn't crash and renders successfully
    assert panel.title.startswith("⚙ TKT-001")


def test_render_column_groups_multiple_tasks():
    t1 = MESTask(id="TKT-001", type=TicketType.CODE, intent="x", raw_input="", requester="a", source="#a")
    t2 = MESTask(id="TKT-002", type=TicketType.SIMPLE, intent="y", raw_input="", requester="b", source="#b")
    panel = render_column([t1, t2])
    assert panel is not None


def test_render_empty_column():
    panel = render_column([])
    assert panel is not None
