"""Tests for Pipeline orchestrator."""

import os

import pytest

from agent_mes.demo.fake_slack import FAKE_SLACK
from agent_mes.integrations.codex import CodexReplayBuilder
from agent_mes.integrations.stubs.blaxel import StubBlaxelVerifier
from agent_mes.integrations.stubs.context_retriever import StubContextRetriever
from agent_mes.integrations.stubs.redis_memory import StubRedisMemory
from agent_mes.integrations.wordware import WordwarePlanner
from agent_mes.pipeline import Pipeline
from agent_mes.schema import MESTask, StageEnum, TicketType
from agent_mes.stages.build import BuildStage
from agent_mes.stages.deploy import DeployStage
from agent_mes.stages.design import DesignStage
from agent_mes.stages.document import DocumentStage
from agent_mes.stages.plan import PlanStage
from agent_mes.stages.review import ReviewStage
from agent_mes.stages.test import TestStage

os.environ["AGENTMES_AUTO_APPROVE"] = "1"


def _build_pipeline() -> Pipeline:
    redis = StubRedisMemory()
    context = StubContextRetriever()
    blaxel = StubBlaxelVerifier()
    return Pipeline(
        plan=PlanStage(wordware=WordwarePlanner(mode="stub")),
        design=DesignStage(redis=redis, context=context),
        build=BuildStage(codex=CodexReplayBuilder(speed=1000.0)),
        test=TestStage(blaxel=blaxel),
        review=ReviewStage(redis=redis, context=context),
        document=DocumentStage(redis=redis),
        deploy=DeployStage(redis=redis, dry_run=True),
    )


def _new_task(ticket_id: str) -> MESTask:
    f = FAKE_SLACK[ticket_id]
    return MESTask(
        id=ticket_id,
        type=TicketType.SIMPLE,
        intent="",
        raw_input=f["raw_text"],
        requester=f["requester"],
        source=f["channel"],
    )


@pytest.mark.asyncio
async def test_pipeline_runs_tkt_002_to_completion():
    pipe = _build_pipeline()
    task = _new_task("TKT-002")
    result = await pipe.run(task)
    assert result.status == "merged"
    assert result.current_stage == StageEnum.DEPLOY
    assert len(result.events) >= 7  # at least one per stage


@pytest.mark.asyncio
async def test_pipeline_runs_tkt_001_with_drift_catch():
    pipe = _build_pipeline()
    task = _new_task("TKT-001")
    result = await pipe.run(task)
    assert result.status == "merged"
    assert result.type == TicketType.CODE
    # 1 plan + 3 design + 1 build + 3 test + (drift + awaiting + approved) = 11+
    assert len(result.events) >= 10
    # Drift caught
    assert any(e.metadata.get("status") == "DRIFT" for e in result.events)
    # Egress kill happened
    assert any("evil.example.com" in str(e.metadata.get("violation", "")) for e in result.events)


@pytest.mark.asyncio
async def test_pipeline_run_parallel_both_tickets():
    pipe = _build_pipeline()
    tasks = [_new_task("TKT-001"), _new_task("TKT-002")]
    results = await pipe.run_parallel(tasks)
    assert len(results) == 2
    assert all(r.status == "merged" for r in results)


@pytest.mark.asyncio
async def test_pipeline_event_callback_fires():
    captured: list[tuple[str, str]] = []

    async def cb(event, task):
        captured.append((task.id, event.action))

    pipe = _build_pipeline()
    pipe.events_callback = cb
    await pipe.run(_new_task("TKT-002"))
    assert len(captured) >= 7
    assert all(tid == "TKT-002" for tid, _ in captured)
