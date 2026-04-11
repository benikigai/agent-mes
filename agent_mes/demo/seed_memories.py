"""Pre-seeded long-term memory pool for the StubRedisMemory.

Includes the adversary memory the Stage 5 drift catch refutes:
the "we already fixed the auth rate limiter on the login service last month"
claim, which is true historically but applies to the wrong endpoint.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

NOW = datetime.now()


def _ago(days: int) -> str:
    return (NOW - timedelta(days=days)).isoformat()


SEED_MEMORIES: list[dict[str, Any]] = [
    # ── The adversary memory (Stage 5 drift catch refutes this) ──
    {
        "id": "mem_0001",
        "text": "we already fixed the auth rate limiter on the login service last month — bumped from 100 to 500 rpm",
        "confidence": 0.9,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(28),
        "topics": ["auth", "rate_limiter", "login"],
    },
    # ── Past code lessons (CODE ticket hydration) ──
    {
        "id": "mem_0002",
        "text": "OAuth refresh tokens should be validated with the leeway parameter, not strict equality",
        "confidence": 0.85,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(45),
        "topics": ["oauth", "refresh", "validation"],
    },
    {
        "id": "mem_0003",
        "text": "blast_radius constraints must be applied at sandbox creation time, not after exec",
        "confidence": 0.95,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(12),
        "topics": ["sandbox", "blast_radius", "isolation"],
    },
    {
        "id": "mem_0004",
        "text": "rate limiter changes need integration tests against the live token refresh path",
        "confidence": 0.8,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(60),
        "topics": ["rate_limiter", "testing", "integration"],
    },
    # ── Past email/knowledge work lessons (SIMPLE ticket hydration) ──
    {
        "id": "mem_0005",
        "text": "incident emails land best when they lead with root cause, then ETA, then mitigation",
        "confidence": 0.88,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(7),
        "topics": ["email", "incident", "tone"],
    },
    {
        "id": "mem_0006",
        "text": "calm tone in incident comms reduces customer escalation by ~30%",
        "confidence": 0.75,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(90),
        "topics": ["email", "tone", "communication"],
    },
    {
        "id": "mem_0007",
        "text": "always include an explicit ETA in status updates — customers prefer 'unknown, will update at 14:00' to silence",
        "confidence": 0.92,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(20),
        "topics": ["email", "status", "communication"],
    },
    # ── Generic past task outcomes ──
    {
        "id": "mem_0008",
        "text": "tasks that touch auth always require human review even if tests pass",
        "confidence": 0.97,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(150),
        "topics": ["auth", "review", "governance"],
    },
    {
        "id": "mem_0009",
        "text": "Codex performs best when given a single function to modify, not a whole module",
        "confidence": 0.7,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(33),
        "topics": ["codex", "build", "scoping"],
    },
    {
        "id": "mem_0010",
        "text": "deploy events should be logged into long-term memory with the PR url so monitoring can correlate",
        "confidence": 0.83,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(15),
        "topics": ["deploy", "monitoring", "observability"],
    },
]
