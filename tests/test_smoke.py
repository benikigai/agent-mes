"""End-to-end smoke test — the gate for 'demo is ready'.

Runs the full pipeline on both tickets via stubs, asserts the choreographed
beats hit identically every rehearsal:

- TKT-001 (CODE flaky test fix) emits a Blaxel egress kill on iter 2
  AND a Stage 5 drift catch referencing inc_226
- TKT-002 (SIMPLE postmortem) emits a Stage 5 drift catch referencing inc_201
- Both end with status='merged'
- Uses AGENTMES_AUTO_APPROVE=1 + dry_run=True
- Completes in <30s
"""

import os
import time

import pytest

from agent_mes.demo.fake_slack import FAKE_SLACK
from agent_mes.integrations.codex import CodexReplayBuilder
from agent_mes.integrations.stubs.blaxel import StubBlaxelVerifier
from agent_mes.integrations.stubs.context_retriever import StubContextRetriever
from agent_mes.integrations.stubs.redis_memory import StubRedisMemory
from agent_mes.integrations.wordware import WordwarePlanner
from agent_mes.pipeline import Pipeline
from agent_mes.schema import MESTask, TicketType
from agent_mes.stages.build import BuildStage
from agent_mes.stages.deploy import DeployStage
from agent_mes.stages.design import DesignStage
from agent_mes.stages.document import DocumentStage
from agent_mes.stages.plan import PlanStage
from agent_mes.stages.review import ReviewStage
from agent_mes.stages.test import TestStage

os.environ["AGENTMES_AUTO_APPROVE"] = "1"


def _make_task(ticket_id: str) -> MESTask:
    f = FAKE_SLACK[ticket_id]
    return MESTask(
        id=ticket_id,
        type=TicketType.SIMPLE,
        intent="",
        raw_input=f["raw_text"],
        requester=f["requester"],
        source=f["channel"],
    )


def _make_pipeline() -> Pipeline:
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


@pytest.mark.asyncio
async def test_smoke_full_pipeline_both_tickets():
    """The big one: full pipeline + both tickets + every choreographed beat."""
    start = time.perf_counter()

    pipeline = _make_pipeline()
    tasks = [_make_task("TKT-001"), _make_task("TKT-002")]
    results = await pipeline.run_parallel(tasks)
    duration = time.perf_counter() - start

    assert all(r.status == "merged" for r in results)
    assert duration < 30.0, f"smoke run took {duration:.1f}s, must be <30s"

    tkt_001 = next(r for r in results if r.id == "TKT-001")
    tkt_002 = next(r for r in results if r.id == "TKT-002")

    # ── TKT-001 (CODE — flaky test fix) ─────────────────────────────
    assert tkt_001.type == TicketType.CODE
    assert len(tkt_001.events) >= 10

    # The Blaxel egress kill on iter 2
    egress = [
        e for e in tkt_001.events
        if e.metadata.get("violation", {}).get("destination") == "evil.example.com"
    ]
    assert len(egress) == 1
    assert egress[0].metadata["violation"]["killed_in_ms"] == 23

    # The Stage 5 drift catch on the "we mocked this" memory
    drift_001 = [e for e in tkt_001.events if e.metadata.get("status") == "DRIFT"]
    assert len(drift_001) >= 1
    assert any(e.metadata.get("prior_incident") == "inc_226" for e in drift_001)

    # The HUMAN approval gate
    assert any(e.agent == "HUMAN" and e.action == "approved" for e in tkt_001.events)

    # ── TKT-002 (SIMPLE — postmortem) ───────────────────────────────
    assert tkt_002.type == TicketType.SIMPLE
    assert len(tkt_002.events) >= 7

    # The Stage 5 drift catch on the "same root cause" memory
    drift_002 = [e for e in tkt_002.events if e.metadata.get("status") == "DRIFT"]
    assert len(drift_002) >= 1
    assert any(e.metadata.get("prior_incident") == "inc_201" for e in drift_002)

    # Both touched all 7 stages
    for task in (tkt_001, tkt_002):
        stages_seen = {e.stage for e in task.events}
        assert len(stages_seen) == 7, f"{task.id} missing stages"
