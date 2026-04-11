"""Tests for the StubRedisMemory choreographed stub."""

import json

import pytest

from agent_mes.integrations.stubs.redis_memory import StubRedisMemory


@pytest.mark.asyncio
async def test_hydrate_flaky_test_query_returns_code_adversary():
    redis = StubRedisMemory()
    memories = await redis.hydrate(query="flaky test mocking race condition", session_id="s1")
    assert len(memories) == 3
    assert any(m["id"] == "mem_0001" for m in memories)
    adversary = next(m for m in memories if m["id"] == "mem_0001")
    assert "mocked" in adversary["text"].lower()


@pytest.mark.asyncio
async def test_hydrate_postmortem_query_returns_simple_adversary():
    redis = StubRedisMemory()
    memories = await redis.hydrate(
        query="draft postmortem for incident rate limit outage",
        session_id="s1",
    )
    assert len(memories) == 3
    assert any(m["id"] == "mem_0002" for m in memories)
    adversary = next(m for m in memories if m["id"] == "mem_0002")
    assert "incident-2026-02-14" in adversary["text"]


@pytest.mark.asyncio
async def test_cross_check_flaky_test_mock_claim_contradicts():
    redis = StubRedisMemory()
    result = await redis.cross_check("we should mock the flaky test for now")
    assert result["contradicted"] is True
    assert result["contradicting"][0]["prior_incident"] == "inc_226"


@pytest.mark.asyncio
async def test_cross_check_postmortem_new_incident_claim_contradicts():
    redis = StubRedisMemory()
    result = await redis.cross_check("rate limiter incident is a new failure mode")
    assert result["contradicted"] is True
    assert result["contradicting"][0]["prior_incident"] == "inc_201"


@pytest.mark.asyncio
async def test_cross_check_unrelated_claim_does_not_contradict():
    redis = StubRedisMemory()
    result = await redis.cross_check("the search service indexes documents nightly")
    assert result["contradicted"] is False


@pytest.mark.asyncio
async def test_write_lesson_appends_to_log_and_returns_id(tmp_path, monkeypatch):
    log_path = tmp_path / "memory_log.jsonl"
    monkeypatch.setattr(
        "agent_mes.integrations.stubs.redis_memory.MEMORY_LOG_PATH",
        log_path,
    )
    redis = StubRedisMemory()
    lesson_id = await redis.write_lesson(
        text="fix race conditions, don't mock them",
        topics=["flaky_test", "race_condition"],
        user_id="usr_sarah",
        negative_constraint=True,
    )
    assert lesson_id.startswith("mem_")
    record = json.loads(log_path.read_text().strip().splitlines()[0])
    assert record["id"] == lesson_id
    assert record["negative_constraint"] is True


@pytest.mark.asyncio
async def test_seed_demo_memories_is_noop():
    redis = StubRedisMemory()
    result = await redis.seed_demo_memories([])
    assert result is None
