"""Tests for ReviewStage. Sets AGENTMES_AUTO_APPROVE=1 to skip input()."""

import os

import pytest

from agent_mes.integrations.stubs.context_retriever import StubContextRetriever
from agent_mes.integrations.stubs.redis_memory import StubRedisMemory
from agent_mes.schema import MemoryProvenance, MESTask, TicketType
from agent_mes.stages.review import ReviewStage

os.environ["AGENTMES_AUTO_APPROVE"] = "1"


@pytest.mark.asyncio
async def test_review_catches_flaky_test_drift_for_tkt_001():
    stage = ReviewStage(redis=StubRedisMemory(), context=StubContextRetriever())
    task = MESTask(
        id="TKT-001",
        type=TicketType.CODE,
        intent="fix flaky test test_oauth_token_refresh",
        raw_input="",
        requester="sarah",
        source="#bugs",
        memory_provenance=[
            MemoryProvenance(
                text="we mocked this same test six months ago — followed by a prod incident",
                confidence=0.92,
                source="agent_memory_seed",
            ),
        ],
    )
    events = await stage.execute(task)
    drift_events = [e for e in events if e.metadata.get("status") == "DRIFT"]
    assert len(drift_events) == 1
    assert drift_events[0].metadata["prior_incident"] == "inc_226"
    assert task.memory_provenance[0].confidence == 0.32  # rounded
    assert any(e.action == "approved" for e in events)
    assert task.human_gates[0].approved is True


@pytest.mark.asyncio
async def test_review_catches_postmortem_drift_for_tkt_002():
    """SIMPLE tickets ALSO fire drift now — postmortem deja vu beat."""
    stage = ReviewStage(redis=StubRedisMemory(), context=StubContextRetriever())
    task = MESTask(
        id="TKT-002",
        type=TicketType.SIMPLE,
        intent="draft postmortem for incident-2026-04-09 rate-limiter outage",
        raw_input="",
        requester="marcus",
        source="#incidents",
        memory_provenance=[
            MemoryProvenance(
                text="incident-2026-02-14 had the same root cause: rate-limiter misconfig from deploy",
                confidence=0.95,
                source="agent_memory_seed",
            ),
        ],
    )
    events = await stage.execute(task)
    drift_events = [e for e in events if e.metadata.get("status") == "DRIFT"]
    assert len(drift_events) == 1
    assert drift_events[0].metadata["prior_incident"] == "inc_201"
    assert any(e.action == "approved" for e in events)
