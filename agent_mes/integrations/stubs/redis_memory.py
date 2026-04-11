"""Choreographed stub of RedisMemoryProtocol.

Returns deterministic seeded data so the demo hits the same beats every
rehearsal. When Vish's real impl lands on vish/redis-blaxel, swap this
import in cli.py for one line — function shapes are identical.

Two adversary memories drive the demo's Stage 5 catches:
  - mem_0001 (CODE-A): "we mocked this test 6mo ago — caused prod incident"
  - mem_0002 (SIMPLE-A): "incident-2026-02-14 had the same root cause"
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_mes.demo.seed_memories import SEED_MEMORIES

MEMORY_LOG_PATH = Path(".demo/memory_log.jsonl")
_LESSON_COUNTER = 4470  # so the first write is mem_4471


class StubRedisMemory:
    """Implements RedisMemoryProtocol with fixture-driven returns."""

    def __init__(self) -> None:
        self._counter = _LESSON_COUNTER
        MEMORY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    async def hydrate(
        self, query: str, session_id: str, limit: int = 3
    ) -> list[dict[str, Any]]:
        """Return up to `limit` seed memories whose topics or text match
        the query string. Always surfaces the right adversary memory for
        the two demo scenarios."""
        query_lower = query.lower()
        scored: list[tuple[int, dict[str, Any]]] = []
        for mem in SEED_MEMORIES:
            score = 0
            for token in query_lower.split():
                if token in mem["text"].lower():
                    score += 2
                if any(token in t for t in mem["topics"]):
                    score += 3
            if score > 0:
                scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [mem for _, mem in scored[:limit]]

        # Force the adversary memory for CODE-A (flaky test scenario)
        if any(k in query_lower for k in ("flaky", "test_oauth", "race", "mock")):
            adversary = next(m for m in SEED_MEMORIES if m["id"] == "mem_0001")
            if adversary not in results:
                results = [adversary] + results[: limit - 1]

        # Force the adversary memory for SIMPLE-A (postmortem scenario)
        if any(k in query_lower for k in ("postmortem", "incident", "rate-limit", "rate limit", "outage")):
            adversary = next(m for m in SEED_MEMORIES if m["id"] == "mem_0002")
            if adversary not in results:
                results = [adversary] + results[: limit - 1]

        # Fall back to first 3 memories so empty queries don't crash
        if not results:
            results = SEED_MEMORIES[:limit]

        return results

    async def cross_check(self, claim: str) -> dict[str, Any]:
        """Return a contradiction record for the two adversary scenarios."""
        c = claim.lower()

        # CODE-A: claim about mocking the flaky test
        if "mock" in c and ("test" in c or "flaky" in c):
            return {
                "contradicted": True,
                "supporting": [],
                "contradicting": [
                    {
                        "memory_id": "mem_0001",
                        "prior_incident": "inc_226",
                        "note": "mocking this test 6 months ago caused a prod incident two weeks later",
                    }
                ],
            }

        # SIMPLE-A: claim about the new incident being unique
        if "incident" in c and ("rate" in c or "limiter" in c or "deploy" in c or "new" in c):
            return {
                "contradicted": True,
                "supporting": [],
                "contradicting": [
                    {
                        "memory_id": "mem_0002",
                        "prior_incident": "inc_201",
                        "note": "incident-2026-02-14 had the same root cause; AI-24 fix never deployed",
                    }
                ],
            }

        return {"contradicted": False, "supporting": [], "contradicting": []}

    async def write_lesson(
        self,
        text: str,
        topics: list[str],
        user_id: str,
        negative_constraint: bool = False,
    ) -> str:
        """Append the lesson to .demo/memory_log.jsonl and return a fake id."""
        self._counter += 1
        lesson_id = f"mem_{self._counter:04d}"
        record = {
            "id": lesson_id,
            "text": text,
            "topics": topics,
            "user_id": user_id,
            "negative_constraint": negative_constraint,
            "written_at": datetime.now().isoformat(),
        }
        with MEMORY_LOG_PATH.open("a") as f:
            f.write(json.dumps(record) + "\n")
        return lesson_id

    async def seed_demo_memories(self, fixtures: list[dict[str, Any]]) -> None:
        """No-op — seed data is loaded from agent_mes.demo.seed_memories."""
        return None
