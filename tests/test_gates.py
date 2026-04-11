"""Tests for agent_mes.web.gates.GateRegistry."""

import asyncio

import pytest

from agent_mes.web.gates import GateRegistry


@pytest.mark.asyncio
async def test_approve_then_wait_returns_immediately():
    gates = GateRegistry()
    gates.approve("TKT-001")
    result = await gates.wait("TKT-001", timeout=1.0)
    assert result is True


@pytest.mark.asyncio
async def test_wait_then_approve_unblocks():
    gates = GateRegistry()

    async def approver():
        await asyncio.sleep(0.05)
        gates.approve("TKT-001")

    waiter = asyncio.create_task(gates.wait("TKT-001", timeout=2.0))
    asyncio.create_task(approver())
    result = await waiter
    assert result is True


@pytest.mark.asyncio
async def test_wait_returns_false_on_timeout():
    gates = GateRegistry()
    result = await gates.wait("TKT-NONEXIST", timeout=0.1)
    assert result is False


@pytest.mark.asyncio
async def test_reset_clears_state():
    gates = GateRegistry()
    gates.approve("TKT-001")
    gates.approve("TKT-002")
    assert "TKT-001" in gates._events
    gates.reset()
    assert gates._events == {}
    # After reset, a new wait on TKT-001 should hit timeout (not auto-resolve)
    result = await gates.wait("TKT-001", timeout=0.1)
    assert result is False


@pytest.mark.asyncio
async def test_register_is_idempotent():
    gates = GateRegistry()
    e1 = gates.register("TKT-001")
    e2 = gates.register("TKT-001")
    assert e1 is e2


@pytest.mark.asyncio
async def test_pending_lists_unset_events():
    gates = GateRegistry()
    gates.register("TKT-001")  # not approved
    gates.approve("TKT-002")
    assert gates.pending == ["TKT-001"]
