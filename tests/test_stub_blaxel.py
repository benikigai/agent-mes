"""Tests for the StubBlaxelVerifier choreographed kill-and-self-heal loop."""

import pytest

from agent_mes.integrations.stubs.blaxel import StubBlaxelVerifier, StubSandbox


@pytest.mark.asyncio
async def test_create_sandbox_returns_stub_sandbox():
    blaxel = StubBlaxelVerifier()
    sandbox = await blaxel.create_sandbox(
        task_id="TKT-001",
        blast_radius={"network_egress": False, "max_cost_usd": 0.5},
    )
    assert isinstance(sandbox, StubSandbox)
    assert sandbox.id == "sbx_TKT-001"
    assert sandbox.iteration == 0


@pytest.mark.asyncio
async def test_self_heal_loop_three_iterations():
    blaxel = StubBlaxelVerifier()
    sandbox = await blaxel.create_sandbox("TKT-001", {})
    result = await blaxel.self_heal_loop(
        sandbox=sandbox,
        code_diff="diff --git a/auth/middleware.py",
        checks=["pytest tests/auth"],
        max_iterations=3,
    )
    assert result["final_status"] == "pass"
    assert len(result["iterations"]) == 3

    iter1, iter2, iter3 = result["iterations"]
    assert iter1["iteration"] == 1
    assert iter1["status"] == "fail"
    assert "ImportError" in iter1["stderr"]

    assert iter2["iteration"] == 2
    assert iter2["status"] == "killed"
    assert iter2["violation"]["destination"] == "evil.example.com"
    assert iter2["violation"]["killed_in_ms"] == 23
    assert "BLAST_RADIUS_VIOLATION" in iter2["violation"]["reason"]

    assert iter3["iteration"] == 3
    assert iter3["status"] == "pass"


@pytest.mark.asyncio
async def test_detect_egress_violation_only_on_iter_2():
    blaxel = StubBlaxelVerifier()
    sandbox = await blaxel.create_sandbox("TKT-001", {})

    sandbox.iteration = 1
    assert await blaxel.detect_egress_violation(sandbox) is None

    sandbox.iteration = 2
    violation = await blaxel.detect_egress_violation(sandbox)
    assert violation is not None
    assert violation["destination"] == "evil.example.com"
    assert violation["killed_in_ms"] == 23

    sandbox.iteration = 3
    assert await blaxel.detect_egress_violation(sandbox) is None


@pytest.mark.asyncio
async def test_run_check_iteration_dependent_results():
    blaxel = StubBlaxelVerifier()
    sandbox = await blaxel.create_sandbox("TKT-001", {})

    sandbox.iteration = 1
    r1 = await blaxel.run_check(sandbox, "pytest")
    assert r1["passed"] is False
    assert "ImportError" in r1["stderr"]

    sandbox.iteration = 3
    r3 = await blaxel.run_check(sandbox, "pytest")
    assert r3["passed"] is True
    assert "5 passed" in r3["stdout"]
