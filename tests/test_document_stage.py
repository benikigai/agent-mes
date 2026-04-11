"""Tests for DocumentStage."""

import pytest

from agent_mes.integrations.stubs.redis_memory import StubRedisMemory
from agent_mes.schema import MESTask, StageEnum, StageEvent, TicketType
from agent_mes.stages.document import DocumentStage


@pytest.mark.asyncio
async def test_document_writes_lesson_with_artifact():
    stage = DocumentStage(redis=StubRedisMemory())
    task = MESTask(
        id="TKT-001",
        type=TicketType.CODE,
        intent="raise the OAuth /v2 rate limit",
        raw_input="",
        requester="sarah",
        source="#bugs",
        events=[
            StageEvent(stage=StageEnum.PLAN, agent="Opus 4.6", action="classified=code"),
            StageEvent(stage=StageEnum.REVIEW, agent="Opus 4.6", action="memory drift",
                       metadata={"status": "DRIFT"}),
        ],
    )
    events = await stage.execute(task)
    assert len(events) == 1
    e = events[0]
    assert e.metadata["lesson_id"].startswith("mem_")
    assert e.metadata["negative_constraint"] is True  # drift was caught earlier
    assert e.artifacts[0].type == "memory"
