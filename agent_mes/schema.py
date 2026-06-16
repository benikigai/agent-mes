"""AgentMES schema — Pydantic v2 models for the MESTask contract.

This is the SHARED INTERFACE between Ben's orchestration code and Vish's
real Redis/Blaxel implementations. Field shapes here MUST stay compatible
with the function signatures locked in the master spec doc — Vish's
integration files build against these types verbatim.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ─── Enums ──────────────────────────────────────────────────────────────────


class TicketType(StrEnum):
    """Two work types AgentMES handles in parallel."""

    SIMPLE = "simple"  # knowledge work — emails, docs, summaries
    CODE = "code"  # code change — features, bugs, refactors


class StageEnum(StrEnum):
    """The 7 stages of the AI-Native Engineering Workflow."""

    PLAN = "plan"
    DESIGN = "design"
    BUILD = "build"
    TEST = "test"
    REVIEW = "review"
    DOCUMENT = "document"
    DEPLOY = "deploy"


class StageResult(StrEnum):
    """Outcome of a single stage execution."""

    PASS = "pass"
    FAIL = "fail"
    BLOCK_FOR_HUMAN = "block_for_human"
    KILLED = "killed"
    REJECTED = "rejected"


class GateDecision(StrEnum):
    """How a human resolved a HumanGate — the tristate the gate mechanism
    carries end to end. REJECTED and TIMED_OUT are distinct so a deliberate
    reject and an unattended timeout render (and transition) differently."""

    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


# ─── Building blocks ────────────────────────────────────────────────────────


class BlastRadius(BaseModel):
    """Constraints on what an agent is allowed to do inside a sandbox."""

    allowed_paths: list[str] = Field(default_factory=list)
    network_egress: bool = False
    max_cost_usd: float = 1.0


class AcceptanceCriterion(BaseModel):
    """A single 'done' check, executable as a machine_check command."""

    description: str
    machine_check: str  # shell command, e.g. "pytest tests/test_auth.py"


class MemoryProvenance(BaseModel):
    """A memory retrieved during Design that the Review stage may verify."""

    text: str
    confidence: float  # 0..1
    source: str  # e.g. "agent_memory_seed"
    retrieved_at: datetime = Field(default_factory=datetime.now)


class Artifact(BaseModel):
    """A produced output worth showing in the receipts."""

    type: Literal["file", "memory", "sandbox", "pr", "email"]
    ref: str  # path / id / url
    summary: str = ""


class StageEvent(BaseModel):
    """A single receipt entry — appended to MESTask.events on every action."""

    timestamp: datetime = Field(default_factory=datetime.now)
    stage: StageEnum
    agent: str  # "Opus 4.6" / "Codex" / "Gemini" / "Blaxel" / "Redis" / "GitHub" / "HUMAN"
    action: str  # short human-readable
    metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)


class HumanGate(BaseModel):
    """A point where a human owns judgment."""

    stage: StageEnum
    prompt: str
    approved: bool | None = None
    approver: str | None = None


# ─── The main task object ──────────────────────────────────────────────────


class MESTask(BaseModel):
    """A unit of work that flows through all 7 stages of the AgentMES pipeline."""

    id: str  # e.g. "TKT-001"
    type: TicketType
    intent: str  # what the requester wants (1-2 sentences)
    raw_input: str  # original message text
    requester: str  # slack handle or user_id
    source: str  # channel + permalink

    blast_radius: BlastRadius = Field(default_factory=BlastRadius)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    context_bundle: dict[str, Any] = Field(default_factory=dict)
    memory_provenance: list[MemoryProvenance] = Field(default_factory=list)

    events: list[StageEvent] = Field(default_factory=list)
    human_gates: list[HumanGate] = Field(default_factory=list)

    current_stage: StageEnum = StageEnum.PLAN
    status: Literal[
        "pending", "running", "blocked", "merged", "killed", "rejected", "expired"
    ] = "pending"


# ─── Task lifecycle state machine ───────────────────────────────────────────
# The bipartite human/agent machine made inspectable: every task.status and the
# states it may legally move to next. Agents drive pending → running → … through
# the throughput stages; humans resolve the `blocked` gates into merged
# (approve), rejected (reject), or expired (gate timeout). Terminal states have
# no successors. ``pipeline.run`` halts the moment a task reaches one.

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"merged", "killed", "rejected", "expired"}
)

TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running"}),
    "running": frozenset({"blocked", "merged", "killed", "rejected", "expired"}),
    "blocked": frozenset({"running", "killed", "rejected", "expired"}),
    "merged": frozenset(),
    "killed": frozenset(),
    "rejected": frozenset(),
    "expired": frozenset(),
}


def can_transition(frm: str, to: str) -> bool:
    """True if a task may legally move from status ``frm`` to status ``to``."""
    return to in TRANSITIONS.get(frm, frozenset())
