"""Choreographed stub of ContextRetrieverProtocol.

Returns Heliograph fixtures so Stage 2 hydration and Stage 5 verification
look real. The Stage 5 contradiction returns a structured discrepancy:
the seed memory's endpoint (/v1/login) vs the current ticket's endpoint
(/v2/oauth) — the demo's structural drift catch.
"""

from __future__ import annotations

from typing import Any

from agent_mes.demo.seed_entities import filter_entities, get_entity


class StubContextRetriever:
    """Implements ContextRetrieverProtocol against the Heliograph fixtures."""

    async def query_entity(self, entity_type: str, entity_id: str) -> dict[str, Any]:
        return get_entity(entity_type, entity_id)

    async def list_related(
        self, entity_type: str, filter_dict: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return filter_entities(entity_type, filter_dict)

    async def verify_claim(self, claim: str, entity_type: str) -> dict[str, Any]:
        """Cross-check a memory claim against live entity records.

        For the auth rate limiter case (the adversary memory), returns a
        structural mismatch: the historical fix was on /v1/login but the
        current ticket is about /v2/oauth.
        """
        claim_lower = claim.lower()
        if "auth rate limit" in claim_lower or (
            "rate limit" in claim_lower and "login" in claim_lower
        ):
            actual_incident = await self.query_entity("incident", "inc_113")
            return {
                "verified": False,
                "actual": {
                    "incident_id": actual_incident["id"],
                    "endpoint": actual_incident["endpoint"],
                    "summary": actual_incident["summary"],
                    "fix_pr_url": actual_incident["fix_pr_url"],
                },
                "discrepancy": (
                    f"endpoint mismatch: memory references "
                    f"{actual_incident['endpoint']} but current task is /v2/oauth"
                ),
            }
        return {
            "verified": True,
            "actual": {},
            "discrepancy": "",
        }
