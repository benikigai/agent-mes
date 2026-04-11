"""Tests for the StubRedisMemory choreographed stub."""

import json
from pathlib import Path

import pytest

from agent_mes.integrations.stubs.redis_memory import StubRedisMemory


@pytest.mark.asyncio
async def test_hydrate_auth_query_returns_adversary_first():
    redis = StubRedisMemory()
    memories = await redis.hydrate(query="oauth rate limit", session_id="s1")
    assert len(memories) == 3
    # adversary memory must be in the result set
    assert any(m["id"] == "mem_0001" for m in memories)
    adversary = next(m for m in memories if m["id"] == "mem_0001")
    assert adversary["confidence"] == 0.9
    assert "rate limiter" in adversary["text"]


@pytest.mark.asyncio
async def test_hydrate_email_query_returns_email_lessons():
    redis = StubRedisMemory()
    memories = await redis.hydrate(query="status update email tone", session_id="s1")
    assert len(memories) == 3
    # at least one email-tagged memory
    assert any("email" in m["topics"] for m in memories)


@pytest.mark.asyncio
async def test_cross_check_auth_rate_limit_contradicts():
    redis = StubRedisMemory()
    result = await redis.cross_check("we already fixed the auth rate limit on the login service")
    assert result["contradicted"] is True
    assert len(result["contradicting"]) == 1
    contradiction = result["contradicting"][0]
    assert contradiction["endpoint_in_memory"] == "/v1/login"
    assert contradiction["endpoint_in_current_task"] == "/v2/oauth"


@pytest.mark.asyncio
async def test_cross_check_unrelated_claim_does_not_contradict():
    redis = StubRedisMemory()
    result = await redis.cross_check("the search service indexes documents")
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
        text="auth rate limit on /v2/oauth raised to 500rpm",
        topics=["auth", "rate_limiter"],
        user_id="usr_sarah",
        negative_constraint=True,
    )
    assert lesson_id.startswith("mem_")
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["id"] == lesson_id
    assert record["negative_constraint"] is True
    assert record["topics"] == ["auth", "rate_limiter"]


@pytest.mark.asyncio
async def test_seed_demo_memories_is_noop():
    redis = StubRedisMemory()
    result = await redis.seed_demo_memories([])
    assert result is None
