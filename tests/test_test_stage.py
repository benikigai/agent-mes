"""Tests for TestStage."""

import pytest

from agent_mes.integrations.stubs.blaxel import StubBlaxelVerifier
from agent_mes.schema import MESTask, TicketType
from agent_mes.stages.test import TestStage


@pytest.mark.asyncio
async def test_test_code_three_iterations_with_egress_kill():
    stage = TestStage(blaxel=StubBlaxelVerifier())
    task = MESTask(
        id="TKT-001",
        type=TicketType.CODE,
        intent="raise the OAuth /v2 rate limit",
        raw_input="",
        requester="sarah",
        source="#bugs",
    )
    events = await stage.execute(task)
    assert len(events) == 3
    statuses = [e.metadata["status"] for e in events]
    assert statuses == ["FAIL", "KILLED", "PASS"]
    # iter 2 has the violation
    iter2 = events[1]
    assert iter2.metadata["violation"]["destination"] == "evil.example.com"
    assert iter2.metadata["violation"]["killed_in_ms"] == 23


@pytest.mark.asyncio
async def test_test_email_one_event():
    stage = TestStage(blaxel=StubBlaxelVerifier())
    task = MESTask(
        id="TKT-002",
        type=TicketType.SIMPLE,
        intent="draft email",
        raw_input="",
        requester="marcus",
        source="#announcements",
    )
    events = await stage.execute(task)
    assert len(events) == 1
    assert events[0].metadata["status"] == "PASS"
    assert "grammar" in events[0].action.lower()
