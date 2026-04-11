"""Tests for ReviewStage. Sets AGENTMES_AUTO_APPROVE=1 to skip input()."""

import os

import pytest

from agent_mes.integrations.stubs.context_retriever import StubContextRetriever
from agent_mes.integrations.stubs.redis_memory import StubRedisMemory
from agent_mes.schema import MemoryProvenance, MESTask, TicketType
from agent_mes.stages.review import ReviewStage

os.environ["AGENTMES_AUTO_APPROVE"] = "1"


@pytest.mark.asyncio
async def test_review_catches_drift_for_tkt_001():
    stage = ReviewStage(redis=StubRedisMemory(), context=StubContextRetriever())
    task = MESTask(
        id="TKT-001",
        type=TicketType.CODE,
        intent="raise the OAuth /v2 rate limit",
        raw_input="",
        requester="sarah",
        source="#bugs",
        memory_provenance=[
            MemoryProvenance(
                text="we already fixed the auth rate limiter on the login service last month",
                confidence=0.9,
                source="agent_memory_seed",
            ),
            MemoryProvenance(
                text="OAuth refresh tokens should be validated with leeway",
                confidence=0.85,
                source="agent_memory_seed",
            ),
        ],
    )
    events = await stage.execute(task)
    drift_events = [e for e in events if e.metadata.get("status") == "DRIFT"]
    assert len(drift_events) == 1
    assert "/v1/login" in drift_events[0].metadata["memory"]
    # Confidence dropped
    assert task.memory_provenance[0].confidence == 0.3
    # Human gate fired
    assert any(e.action == "approved" for e in events)
    assert task.human_gates[0].approved is True


@pytest.mark.asyncio
async def test_review_no_drift_for_tkt_002():
    stage = ReviewStage(redis=StubRedisMemory(), context=StubContextRetriever())
    task = MESTask(
        id="TKT-002",
        type=TicketType.SIMPLE,
        intent="draft email",
        raw_input="",
        requester="marcus",
        source="#announcements",
        memory_provenance=[
            MemoryProvenance(
                text="incident emails land best when they lead with root cause",
                confidence=0.88,
                source="agent_memory_seed",
            ),
        ],
    )
    events = await stage.execute(task)
    assert all(e.metadata.get("status") != "DRIFT" for e in events)
    assert len(events) == 1
    assert events[0].metadata["status"] == "PASS"
