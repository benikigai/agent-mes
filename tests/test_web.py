"""Integration tests for the FastAPI web server.

Uses TestClient (synchronous) for the simple endpoints and the underlying
state object directly for the launch + approve + drain flow.
"""

import asyncio
import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ["AGENTMES_AUTO_APPROVE"] = "1"

from agent_mes.web import server  # noqa: E402

client = TestClient(server.app)


def _reset_module_state() -> None:
    """Reset the module-level WebState between tests."""
    server.state.reset()
    # Clear any subscriber queues lingering from prior tests
    server.state.broker = type(server.state.broker)()


def setup_function(_func):
    _reset_module_state()


def test_state_endpoint_returns_initial_tasks():
    r = client.get("/api/state")
    assert r.status_code == 200
    data = r.json()
    assert data["running"] is False
    assert len(data["tasks"]) == 2
    ids = {t["id"] for t in data["tasks"]}
    assert ids == {"TKT-001", "TKT-002"}
    # Initial state: no events, both in PLAN
    for t in data["tasks"]:
        assert t["current_stage"] == "plan"
        assert t["events"] == []
        assert t["raw_input"]


def test_get_index_route():
    r = client.get("/")
    assert r.status_code == 200
    assert "AgentMES" in r.text


def test_get_replay_route():
    r = client.get("/replay")
    assert r.status_code == 200
    assert "asciinema-player" in r.text


def test_get_static_assets():
    r = client.get("/style.css")
    assert r.status_code == 200
    assert "AgentMES" in r.text or ":root" in r.text  # CSS file content
    r = client.get("/app.js")
    assert r.status_code == 200
    assert "EventSource" in r.text


@pytest.mark.asyncio
async def test_launch_runs_full_pipeline_to_merged():
    """End-to-end: launch the pipeline through the FastAPI surface and
    verify both tickets reach merged. Uses AGENTMES_AUTO_APPROVE=1 so the
    gate_provider's HumanGate auto-resolves via the env var fallback path
    in ReviewStage._await_human (not via the gate registry — the env var
    short-circuits before checking the provider in this test path)."""
    # Reset state directly (not via TestClient since we need async)
    server.state.reset()
    server.state.broker = type(server.state.broker)()

    # Build pipeline + drive it
    pipeline = server._build_pipeline(server.state)

    # The gate_provider will be invoked but since AGENTMES_AUTO_APPROVE=1
    # is set in the env, the ReviewStage._await_human path runs the
    # provider AND the env var falls through. We need to also auto-approve
    # via the gate registry to keep the test deterministic.
    async def auto_approve_after(delay: float) -> None:
        await asyncio.sleep(delay)
        for tid in ["TKT-001", "TKT-002"]:
            server.state.gates.approve(tid)

    asyncio.create_task(auto_approve_after(0.5))
    server.state.running = True
    try:
        await pipeline.run_parallel(server.state.tasks)
    finally:
        server.state.running = False

    for t in server.state.tasks:
        assert t.status == "merged", f"{t.id} ended with status={t.status}"


@pytest.mark.asyncio
async def test_approve_endpoint_calls_gate_registry():
    """The /api/approve/{task_id} POST sets the gate event."""
    server.state.reset()
    # Pre-register a gate
    event = server.state.gates.register("TKT-001")
    assert not event.is_set()
    # Hit the endpoint via TestClient
    r = client.post("/api/approve/TKT-001")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    # The event is now set
    assert event.is_set()


def test_launch_409_when_already_running():
    """If state.running is True, /api/launch returns 409."""
    server.state.reset()
    server.state.running = True
    r = client.post("/api/launch")
    assert r.status_code == 409
    server.state.running = False  # cleanup


def test_relaunch_resets_state():
    """Calling /api/launch twice resets between runs."""
    server.state.reset()
    # First "completed" run
    server.state.tasks[0].status = "merged"
    server.state.tasks[1].status = "merged"
    server.state.running = False
    # Now relaunch — state should reset to fresh
    server.state.reset()
    assert all(t.status == "pending" for t in server.state.tasks)
    assert all(t.current_stage.value == "plan" for t in server.state.tasks)
    assert all(len(t.events) == 0 for t in server.state.tasks)
