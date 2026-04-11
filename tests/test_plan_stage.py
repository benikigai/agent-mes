"""Tests for PlanStage."""

import pytest

from agent_mes.demo.fake_slack import FAKE_SLACK
from agent_mes.integrations.wordware import WordwarePlanner
from agent_mes.schema import MESTask, StageEnum, TicketType
from agent_mes.stages.plan import PlanStage


def _new_task(ticket_id: str) -> MESTask:
    f = FAKE_SLACK[ticket_id]
    return MESTask(
        id=ticket_id,
        type=TicketType.SIMPLE,  # gets reclassified by PlanStage
        intent="",
        raw_input=f["raw_text"],
        requester=f["requester"],
        source=f["channel"],
    )


@pytest.mark.asyncio
async def test_plan_classifies_tkt_001_as_code():
    stage = PlanStage(wordware=WordwarePlanner(mode="stub"))
    task = _new_task("TKT-001")
    events = await stage.execute(task)
    assert len(events) == 1
    assert task.type == TicketType.CODE
    assert len(task.acceptance_criteria) == 3
    assert task.intent.startswith("raise the OAuth")
    assert events[0].metadata["status"] == "PASS"


@pytest.mark.asyncio
async def test_plan_classifies_tkt_002_as_simple():
    stage = PlanStage(wordware=WordwarePlanner(mode="stub"))
    task = _new_task("TKT-002")
    events = await stage.execute(task)
    assert len(events) == 1
    assert task.type == TicketType.SIMPLE
    assert task.intent.startswith("draft a status-update")
    assert task.current_stage == StageEnum.PLAN
    assert task.human_gates[0].approved is True
