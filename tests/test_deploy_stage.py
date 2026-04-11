"""Tests for DeployStage. Uses dry_run=True to avoid real PR creation."""

from pathlib import Path

import pytest

from agent_mes.integrations.stubs.redis_memory import StubRedisMemory
from agent_mes.schema import MESTask, StageEnum, StageEvent, TicketType
from agent_mes.stages.deploy import DeployStage


@pytest.mark.asyncio
async def test_deploy_code_dry_run_prints_gh_command():
    stage = DeployStage(redis=StubRedisMemory(), dry_run=True)
    task = MESTask(
        id="TKT-001",
        type=TicketType.CODE,
        intent="raise the OAuth /v2 rate limit",
        raw_input="",
        requester="sarah",
        source="#bugs",
        events=[
            StageEvent(stage=StageEnum.PLAN, agent="Opus 4.6", action="classified=code"),
        ],
    )
    events = await stage.execute(task)
    assert len(events) == 1
    e = events[0]
    assert "dry-run" in e.metadata["pr_url"]
    assert e.artifacts[0].type == "pr"
    assert task.status == "merged"


@pytest.mark.asyncio
async def test_deploy_email_writes_file():
    stage = DeployStage(redis=StubRedisMemory(), dry_run=True)
    task = MESTask(
        id="TKT-002",
        type=TicketType.SIMPLE,
        intent="draft email",
        raw_input="",
        requester="marcus",
        source="#announcements",
        context_bundle={"email_body": "Hi team, status update follows."},
    )
    events = await stage.execute(task)
    assert len(events) == 1
    e = events[0]
    assert e.artifacts[0].type == "email"
    out_path = Path(e.artifacts[0].ref)
    assert out_path.exists()
    assert "status update" in out_path.read_text()
    assert task.status == "merged"
