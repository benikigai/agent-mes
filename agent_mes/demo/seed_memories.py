"""Pre-seeded long-term memory pool for the StubRedisMemory.

Includes the two adversary memories the Stage 5 drift catch fires on:

- mem_0001: "we mocked this same test 6 months ago — caused prod incident next sprint"
            (the trap for CODE-A flaky test fix — confirms Codex was right not to mock)
- mem_0002: "incident-2026-02-14 had the same root cause: rate-limiter misconfig in the
            same deploy pipeline. fix was proposed but never deployed."
            (the trap for SIMPLE-A postmortem — same fire, never put out for real)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

NOW = datetime.now()


def _ago(days: int) -> str:
    return (NOW - timedelta(days=days)).isoformat()


SEED_MEMORIES: list[dict[str, Any]] = [
    # ── ADVERSARY #1 (for CODE-A flaky test fix) ──
    {
        "id": "mem_0001",
        "text": "we mocked this same test six months ago — followed by a prod incident the next sprint when the race condition fired in production",
        "confidence": 0.92,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(180),
        "topics": ["flaky_test", "mocking", "race_condition", "oauth"],
    },
    # ── ADVERSARY #2 (for SIMPLE-A postmortem) ──
    {
        "id": "mem_0002",
        "text": "incident-2026-02-14 had the same root cause as 04-09 — rate-limiter misconfig from the same deploy pipeline. action item AI-24 proposed a deploy validation gate but it was never implemented.",
        "confidence": 0.95,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(56),
        "topics": ["postmortem", "rate_limiter", "deploy_pipeline", "incident"],
    },
    # ── Past code lessons (CODE ticket hydration) ──
    {
        "id": "mem_0003",
        "text": "race conditions in token refresh flows usually need a distributed lock, not a retry-with-backoff",
        "confidence": 0.85,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(45),
        "topics": ["race_condition", "lock", "oauth", "refresh"],
    },
    {
        "id": "mem_0004",
        "text": "blast_radius constraints must be applied at sandbox creation time, not after exec",
        "confidence": 0.95,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(12),
        "topics": ["sandbox", "blast_radius", "isolation"],
    },
    {
        "id": "mem_0005",
        "text": "flaky tests that pass on retry but fail under load almost always indicate a real production race",
        "confidence": 0.88,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(60),
        "topics": ["flaky_test", "race_condition", "production"],
    },
    # ── Postmortem / incident knowledge work lessons (SIMPLE hydration) ──
    {
        "id": "mem_0006",
        "text": "postmortems land best when each action item has an owner, a due date, and a verification step",
        "confidence": 0.93,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(7),
        "topics": ["postmortem", "action_items", "ownership"],
    },
    {
        "id": "mem_0007",
        "text": "5 Whys analysis works only if the team is willing to go past the first 'human error' answer — keep digging",
        "confidence": 0.9,
        "source": "agent_memory_seed",
        "retrieved_at": _ago(20),
        "topics": ["postmortem", "5_whys", "root_cause"],
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
