"""Tests for WordwarePlanner stub mode."""

import pytest

from agent_mes.demo.fake_slack import FAKE_SLACK
from agent_mes.integrations.wordware import WordwarePlanner


@pytest.mark.asyncio
async def test_stub_mode_returns_tkt_001_payload_for_oauth_request():
    planner = WordwarePlanner(mode="stub")
    fixture = FAKE_SLACK["TKT-001"]
    result = await planner.plan_from_slack(
        raw_text=fixture["raw_text"],
        requester=fixture["requester"],
        channel=fixture["channel"],
    )
    assert result == fixture["plan_payload"]
    assert result["blast_radius"]["network_egress"] is False
    assert len(result["acceptance_criteria"]) == 3


@pytest.mark.asyncio
async def test_stub_mode_returns_tkt_002_payload_for_email_request():
    planner = WordwarePlanner(mode="stub")
    fixture = FAKE_SLACK["TKT-002"]
    result = await planner.plan_from_slack(
        raw_text=fixture["raw_text"],
        requester=fixture["requester"],
        channel=fixture["channel"],
    )
    assert result == fixture["plan_payload"]


@pytest.mark.asyncio
async def test_real_mode_without_url_raises():
    planner = WordwarePlanner(mode="real")
    with pytest.raises(RuntimeError, match="flow_url"):
        await planner.plan_from_slack("hi", "ben", "#general")
