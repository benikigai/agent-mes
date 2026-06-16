"""R2 — the real bipartite state machine.

Pins the behavior the redesign review flagged as broken: a rejected Review gate
must HALT the pipeline (the old code logged "rejected" then set status="running"
and merged anyway), reject and timeout must be distinguishable, and the
transition table must describe the machine the pipeline actually runs.
"""

import pytest
from fastapi.testclient import TestClient

from agent_mes import pipeline as pipeline_mod
from agent_mes.integrations.codex import CodexReplayBuilder
from agent_mes.integrations.stubs.blaxel import StubBlaxelVerifier
from agent_mes.integrations.stubs.context_retriever import StubContextRetriever
from agent_mes.integrations.stubs.redis_memory import StubRedisMemory
from agent_mes.integrations.wordware import WordwarePlanner
from agent_mes.pipeline import Pipeline
from agent_mes.schema import (
    TERMINAL_STATUSES,
    TRANSITIONS,
    GateDecision,
    StageEnum,
    can_transition,
)
from agent_mes.stages.build import BuildStage
from agent_mes.stages.deploy import DeployStage
from agent_mes.stages.design import DesignStage
from agent_mes.stages.document import DocumentStage
from agent_mes.stages.plan import PlanStage
from agent_mes.stages.review import ReviewStage
from agent_mes.stages.test import TestStage
from agent_mes.web import server
from agent_mes.web.gates import GateRegistry

client = TestClient(server.app)


def _controlled_pipeline(monkeypatch, decisions: dict) -> Pipeline:
    """A real 7-stage pipeline whose human gates resolve to fixed decisions
    (keyed by StageEnum, default APPROVED). Dwell zeroed; deploy dry-run."""
    monkeypatch.setattr(pipeline_mod, "STAGE_DWELL_SECONDS", 0)
    redis = StubRedisMemory()
    context = StubContextRetriever()

    async def gate(g):
        return decisions.get(g.stage, GateDecision.APPROVED)

    return Pipeline(
        plan=PlanStage(wordware=WordwarePlanner(mode="stub")),
        design=DesignStage(redis=redis, context=context),
        build=BuildStage(codex=CodexReplayBuilder(speed=1000.0)),
        test=TestStage(blaxel=StubBlaxelVerifier()),
        review=ReviewStage(redis=redis, context=context, gate_provider=gate),
        document=DocumentStage(redis=redis),
        deploy=DeployStage(redis=redis, dry_run=True, gate_provider=gate),
    )


# ─── the headline fix: reject HALTS, it does not merge ───────────────────────


async def test_review_reject_halts_does_not_merge(monkeypatch):
    p = _controlled_pipeline(monkeypatch, {StageEnum.REVIEW: GateDecision.REJECTED})
    task = server._new_task("TKT-001")  # CODE ticket with choreographed drift
    await p.run(task)
    assert task.status == "rejected", "a rejected review must close the ticket"
    assert task.current_stage == StageEnum.REVIEW, "must not advance past Review"
    assert not any(e.metadata.get("status") == "PASS" and "merged" in e.action for e in task.events)


async def test_review_timeout_expires(monkeypatch):
    p = _controlled_pipeline(monkeypatch, {StageEnum.REVIEW: GateDecision.TIMED_OUT})
    task = server._new_task("TKT-001")
    await p.run(task)
    assert task.status == "expired"
    assert task.current_stage == StageEnum.REVIEW


async def test_full_approve_merges(monkeypatch):
    p = _controlled_pipeline(monkeypatch, {})  # all gates APPROVED
    task = server._new_task("TKT-001")
    await p.run(task)
    assert task.status == "merged"
    assert task.current_stage == StageEnum.DEPLOY


async def test_deploy_reject_closes_ticket(monkeypatch):
    # Review approves, Deploy rejects — the ship-it gate, not the drift gate.
    p = _controlled_pipeline(monkeypatch, {StageEnum.DEPLOY: GateDecision.REJECTED})
    task = server._new_task("TKT-001")
    await p.run(task)
    assert task.status == "rejected"
    assert task.current_stage == StageEnum.DEPLOY


# ─── the gate mechanism carries a real decision ──────────────────────────────


async def test_gate_registry_delivers_decision():
    reg = GateRegistry()
    reg.approve("a:review")
    reg.reject("b:deploy")
    assert await reg.wait("a:review", timeout=1.0) == GateDecision.APPROVED
    assert await reg.wait("b:deploy", timeout=1.0) == GateDecision.REJECTED


async def test_gate_registry_timeout_is_distinct():
    reg = GateRegistry()
    assert await reg.wait("nobody", timeout=0.05) == GateDecision.TIMED_OUT


async def test_gate_decision_order_independent():
    """A decision recorded before the stage waits is still delivered."""
    reg = GateRegistry()
    reg.reject("k")  # resolved first
    assert await reg.wait("k", timeout=1.0) == GateDecision.REJECTED


# ─── the transition table describes the real machine ─────────────────────────


def test_transition_table_well_formed():
    statuses = {"pending", "running", "blocked", "merged", "killed", "rejected", "expired"}
    assert set(TRANSITIONS) == statuses, "every status must be a key"
    for terminal in TERMINAL_STATUSES:
        assert TRANSITIONS[terminal] == frozenset(), f"{terminal} must have no successors"
    # Successors must themselves be valid statuses.
    for frm, tos in TRANSITIONS.items():
        for to in tos:
            assert to in statuses
    # The transitions the pipeline actually performs.
    assert can_transition("pending", "running")
    assert can_transition("running", "blocked")
    assert can_transition("blocked", "running")
    assert can_transition("running", "merged")
    assert can_transition("blocked", "rejected")
    assert can_transition("blocked", "expired")
    # Illegal: a blocked gate cannot jump straight to merged, terminals are dead.
    assert not can_transition("blocked", "merged")
    assert not can_transition("merged", "running")
    assert not can_transition("rejected", "running")


# ─── the /api/reject endpoint + stale-click guard ────────────────────────────


def test_reject_endpoint_resolves_gate():
    server.state.reset()
    task = server.state.tasks[0]
    r = client.post(f"/api/reject/{task.id}")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_unknown_task_404():
    assert client.post("/api/reject/NOPE").status_code == 404
    assert client.post("/api/approve/NOPE").status_code == 404


def test_stage_mismatch_409():
    server.state.reset()
    task = server.state.tasks[0]  # fresh task is parked at 'plan'
    assert client.post(f"/api/approve/{task.id}", json={"stage": "deploy"}).status_code == 409
    assert client.post(f"/api/reject/{task.id}", json={"stage": "deploy"}).status_code == 409
    # Naming the correct stage (or none) is accepted.
    assert client.post(f"/api/approve/{task.id}", json={"stage": "plan"}).status_code == 200
