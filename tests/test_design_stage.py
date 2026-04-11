"""Tests for DesignStage."""

import pytest

from agent_mes.integrations.stubs.context_retriever import StubContextRetriever
from agent_mes.integrations.stubs.redis_memory import StubRedisMemory
from agent_mes.schema import MESTask, TicketType
from agent_mes.stages.design import DesignStage


@pytest.mark.asyncio
async def test_design_emits_three_events_and_hydrates():
    stage = DesignStage(redis=StubRedisMemory(), context=StubContextRetriever())
    task = MESTask(
        id="TKT-001",
        type=TicketType.CODE,
        intent="raise the OAuth /v2 rate limit so token refresh stops 429ing",
        raw_input="",
        requester="sarah",
        source="#bugs",
    )
    events = await stage.execute(task)
    assert len(events) == 3
    agents = [e.agent for e in events]
    assert agents == ["Opus 4.6", "Codex", "Gemini"]
    assert len(task.memory_provenance) == 3
    assert task.context_bundle["service"]["name"] == "auth-service"
    assert task.context_bundle["memories_retrieved"] == 3
