"""Tests for agent_mes.web.events.EventBroker."""

import pytest

from agent_mes.schema import MESTask, StageEnum, StageEvent, TicketType
from agent_mes.web.events import EventBroker


def _task() -> MESTask:
    return MESTask(
        id="TKT-001",
        type=TicketType.CODE,
        intent="fix the flaky test",
        raw_input="please fix",
        requester="sarah",
        source="#bugs",
    )


def _event() -> StageEvent:
    return StageEvent(
        stage=StageEnum.PLAN,
        agent="Opus 4.6",
        action="classified=code",
        metadata={"ac_count": 3, "status": "PASS"},
    )


@pytest.mark.asyncio
async def test_subscribe_returns_queue():
    broker = EventBroker()
    q = broker.subscribe()
    assert broker.subscriber_count == 1
    assert q.empty()


@pytest.mark.asyncio
async def test_publish_delivers_payload_shape():
    broker = EventBroker()
    q = broker.subscribe()
    task = _task()
    event = _event()
    task.events.append(event)  # the pipeline appends BEFORE firing the callback
    await broker.publish(event, task)

    payload = await q.get()
    assert payload["type"] == "event"
    assert payload["task_id"] == "TKT-001"
    assert payload["event"]["agent"] == "Opus 4.6"
    assert payload["event"]["action"] == "classified=code"
    assert payload["task"]["id"] == "TKT-001"
    assert payload["task"]["type"] == "code"
    assert payload["task"]["raw_input"] == "please fix"
    assert payload["task"]["events"][0]["agent"] == "Opus 4.6"


@pytest.mark.asyncio
async def test_two_subscribers_both_receive():
    broker = EventBroker()
    q1 = broker.subscribe()
    q2 = broker.subscribe()
    task = _task()
    task.events.append(_event())
    await broker.publish(_event(), task)

    p1 = await q1.get()
    p2 = await q2.get()
    assert p1 == p2
    assert p1["task_id"] == "TKT-001"


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    broker = EventBroker()
    q = broker.subscribe()
    broker.unsubscribe(q)
    assert broker.subscriber_count == 0
    task = _task()
    await broker.publish(_event(), task)
    assert q.empty()  # nothing was delivered after unsubscribe


@pytest.mark.asyncio
async def test_unsubscribe_unknown_queue_is_safe():
    import asyncio
    broker = EventBroker()
    other: asyncio.Queue = asyncio.Queue()
    broker.unsubscribe(other)  # should not raise
    assert broker.subscriber_count == 0


def test_current_state_snapshot():
    broker = EventBroker()
    tasks = [_task()]
    snapshot = broker.current_state(tasks)
    assert snapshot["type"] == "state"
    assert len(snapshot["tasks"]) == 1
    assert snapshot["tasks"][0]["id"] == "TKT-001"
