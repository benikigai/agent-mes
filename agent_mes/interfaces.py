"""Protocol classes for swappable backends.

Stubs and real implementations both satisfy these Protocols. The pipeline
takes them via constructor injection so swapping stub → real is a single
import-line change in cli.py.

Function signatures here MUST match the master spec doc verbatim — Vish's
real implementations on the vish/redis-blaxel branch build against these.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Awaitable, Callable, Protocol, runtime_checkable

from agent_mes.schema import GateDecision, HumanGate

# The browser-driven (or stdin) human-gate hook. Given the HumanGate the stage
# is parked at, returns how the human resolved it. Replaces the two duplicate
# ``GateProvider = Callable[[HumanGate], Awaitable[bool]]`` aliases that used to
# live in review.py and deploy.py — and upgrades bool → GateDecision so reject
# and timeout are distinguishable.
HumanGateProvider = Callable[[HumanGate], Awaitable[GateDecision]]


# ─── Sandbox handle (returned by BlaxelVerifier.create_sandbox) ─────────────


@runtime_checkable
class Sandbox(Protocol):
    """Opaque handle the orchestrator passes back into the verifier."""

    id: str
    iteration: int


# ─── Sponsor backends ───────────────────────────────────────────────────────


@runtime_checkable
class RedisMemoryProtocol(Protocol):
    """Long-term semantic memory — Redis Agent Memory Server (Vish)."""

    async def hydrate(self, query: str, session_id: str, limit: int = 3) -> list[dict[str, Any]]:
        """DESIGN STAGE — semantic recall. Returns memory dicts with
        text/confidence/source/retrieved_at."""
        ...

    async def cross_check(self, claim: str) -> dict[str, Any]:
        """REVIEW STAGE — search long-term memory for contradicting/supporting
        records for the given claim. Returns
        {contradicted: bool, supporting: [...], contradicting: [...]}."""
        ...

    async def write_lesson(
        self,
        text: str,
        topics: list[str],
        user_id: str,
        negative_constraint: bool = False,
    ) -> str:
        """DOCUMENT STAGE — persist a decision log to long-term memory.
        Returns the new memory id."""
        ...

    async def seed_demo_memories(self, fixtures: list[dict[str, Any]]) -> None:
        """Bulk-load fixture memories at startup (used by demo seed)."""
        ...


@runtime_checkable
class ContextRetrieverProtocol(Protocol):
    """Schema-typed ground-truth retrieval — Redis Context Surfaces (Vish)."""

    async def query_entity(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        """DESIGN STAGE — single-record lookup from the surface."""
        ...

    async def list_related(
        self, entity_type: str, filter_dict: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """DESIGN STAGE — filtered query against the surface."""
        ...

    async def verify_claim(self, claim: str, entity_type: str) -> dict[str, Any]:
        """REVIEW STAGE — cross-check a memory claim against live entity
        records. Returns {verified: bool, actual: {...}, discrepancy: str}."""
        ...


@runtime_checkable
class BlaxelVerifierProtocol(Protocol):
    """microVM verification sandbox — Blaxel (Vish)."""

    async def create_sandbox(
        self, task_id: str, blast_radius: dict[str, Any]
    ) -> Sandbox:
        """TEST STAGE — spin up a microVM with blast_radius applied."""
        ...

    async def run_check(self, sandbox: Sandbox, machine_check: str) -> dict[str, Any]:
        """TEST STAGE — execute a single acceptance criterion inside the
        sandbox. Returns {passed: bool, stderr: str, stdout: str}."""
        ...

    async def self_heal_loop(
        self,
        sandbox: Sandbox,
        code_diff: str,
        checks: list[str],
        max_iterations: int = 3,
    ) -> dict[str, Any]:
        """TEST STAGE — orchestrate the iterate-until-pass loop. Returns
        {iterations: [...], final_status: 'pass'|'fail'|'killed'}."""
        ...

    async def detect_egress_violation(self, sandbox: Sandbox) -> dict[str, Any] | None:
        """TEST STAGE — return violation log if the sandbox phoned home;
        None otherwise. {violated_at: iso, destination: str, killed_in_ms: int}."""
        ...


@runtime_checkable
class WordwarePlannerProtocol(Protocol):
    """Natural-language compiler — Wordware (Ben)."""

    async def plan_from_slack(
        self, raw_text: str, requester: str, channel: str
    ) -> dict[str, Any]:
        """PLAN STAGE — translate raw Slack text into MESTask first-stage
        payload. Returns dict with intent/acceptance_criteria/blast_radius hints."""
        ...


@runtime_checkable
class CodexBuilderProtocol(Protocol):
    """Code generation — OpenAI Codex (Ben, replay mode)."""

    def build(self, task: Any) -> AsyncIterator[str]:
        """BUILD STAGE — async generator yielding output lines from the
        recorded Codex session at controlled playback speed."""
        ...
