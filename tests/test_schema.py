"""Tests for agent_mes.schema — round-trip + enum sanity."""

from agent_mes.schema import (
    AcceptanceCriterion,
    Artifact,
    BlastRadius,
    HumanGate,
    MemoryProvenance,
    MESTask,
    StageEnum,
    StageEvent,
    StageResult,
    TicketType,
)


def test_enum_values_match_spec():
    assert TicketType.SIMPLE == "simple"
    assert TicketType.CODE == "code"

    assert StageEnum.PLAN == "plan"
    assert StageEnum.DESIGN == "design"
    assert StageEnum.BUILD == "build"
    assert StageEnum.TEST == "test"
    assert StageEnum.REVIEW == "review"
    assert StageEnum.DOCUMENT == "document"
    assert StageEnum.DEPLOY == "deploy"

    assert StageResult.PASS == "pass"
    assert StageResult.FAIL == "fail"
    assert StageResult.BLOCK_FOR_HUMAN == "block_for_human"
    assert StageResult.KILLED == "killed"


def test_minimal_mestask_round_trip():
    task = MESTask(
        id="TKT-001",
        type=TicketType.CODE,
        intent="fix oauth rate limit on /v2",
        raw_input="auth /v2 is rate limited too aggressively",
        requester="sarah",
        source="#bugs",
    )
    dumped = task.model_dump(mode="json")
    restored = MESTask.model_validate(dumped)
    assert restored == task


def test_mestask_with_full_history():
    task = MESTask(
        id="TKT-002",
        type=TicketType.SIMPLE,
        intent="send a status update email",
        raw_input="please send an update",
        requester="marcus",
        source="#announce",
        blast_radius=BlastRadius(allowed_paths=["drafts/"], network_egress=False, max_cost_usd=0.05),
        acceptance_criteria=[
            AcceptanceCriterion(description="email under 200 words", machine_check="echo wc"),
        ],
        memory_provenance=[
            MemoryProvenance(text="prior email tone was warm", confidence=0.8, source="seed"),
        ],
        events=[
            StageEvent(
                stage=StageEnum.PLAN,
                agent="Opus 4.6",
                action="classified=simple",
                metadata={"ac_count": 1},
                artifacts=[Artifact(type="file", ref="drafts/draft1.md", summary="initial")],
            ),
        ],
        human_gates=[HumanGate(stage=StageEnum.REVIEW, prompt="ok to send?")],
        current_stage=StageEnum.PLAN,
        status="running",
    )
    dumped = task.model_dump(mode="json")
    restored = MESTask.model_validate(dumped)
    assert restored.id == "TKT-002"
    assert restored.events[0].agent == "Opus 4.6"
    assert restored.events[0].artifacts[0].ref == "drafts/draft1.md"
    assert restored.human_gates[0].approved is None
