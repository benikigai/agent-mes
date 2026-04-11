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
        intent="raise the OAuth /v2 rate limit",
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
async def test_build_email_emits_word_count_and_stashes_body():
    stage = BuildStage(codex=CodexReplayBuilder(speed=1000.0))
    task = MESTask(
        id="TKT-002",
        type=TicketType.SIMPLE,
        intent="draft a status email",
        raw_input="",
        requester="marcus",
        source="#announcements",
    )
    events = await stage.execute(task)
    assert len(events) == 1
    assert events[0].metadata["word_count"] > 50
    assert "email_body" in task.context_bundle
    assert events[0].artifacts[0].type == "email"
