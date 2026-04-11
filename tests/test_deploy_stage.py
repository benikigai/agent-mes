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
        intent="fix flaky test test_oauth_token_refresh",
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
async def test_deploy_postmortem_writes_file():
    stage = DeployStage(redis=StubRedisMemory(), dry_run=True)
    task = MESTask(
        id="TKT-002",
        type=TicketType.SIMPLE,
        intent="draft postmortem",
        raw_input="",
        requester="marcus",
        source="#incidents",
        context_bundle={"email_body": "# Postmortem: incident-2026-04-09\nFull body here."},
    )
    events = await stage.execute(task)
    assert len(events) == 1
    e = events[0]
    assert e.artifacts[0].type == "email"
    out_path = Path(e.artifacts[0].ref)
    assert out_path.exists()
    assert out_path.name.startswith("postmortem-")
    assert "Postmortem" in out_path.read_text()
    assert task.status == "merged"
    assert e.metadata["posted_to"] == "#incidents"
