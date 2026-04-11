"""Tests for BuildStage."""

import pytest

from agent_mes.integrations.codex import CodexReplayBuilder
from agent_mes.schema import MESTask, TicketType
from agent_mes.stages.build import BuildStage


@pytest.mark.asyncio
async def test_build_code_emits_diff_metadata():
    stage = BuildStage(codex=CodexReplayBuilder(speed=1000.0))
    task = MESTask(
        id="TKT-001",
        type=TicketType.CODE,
        intent="fix flaky test test_oauth_token_refresh",
        raw_input="",
        requester="sarah",
        source="#bugs",
    )
    events = await stage.execute(task)
    assert len(events) == 1
    e = events[0]
    assert e.metadata["lines_added"] == 47
    assert e.metadata["lines_removed"] == 3
    assert "auth/middleware.py" in e.metadata["files"]
    assert e.artifacts[0].type == "file"


@pytest.mark.asyncio
async def test_build_postmortem_emits_action_items_and_stashes_body():
    stage = BuildStage(codex=CodexReplayBuilder(speed=1000.0))
    task = MESTask(
        id="TKT-002",
        type=TicketType.SIMPLE,
        intent="draft postmortem",
        raw_input="",
        requester="marcus",
        source="#incidents",
    )
    events = await stage.execute(task)
    assert len(events) == 1
    e = events[0]
    assert e.metadata["action_items"] >= 3
    assert e.metadata["five_whys"] >= 5
    assert e.metadata["channel"] == "#incidents"
    assert "email_body" in task.context_bundle
    assert "Postmortem" in task.context_bundle["email_body"]
