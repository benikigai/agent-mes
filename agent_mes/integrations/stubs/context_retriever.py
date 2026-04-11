"""Choreographed stub of ContextRetrieverProtocol.

Returns Heliograph fixtures so Stage 2 hydration and Stage 5 verification
look real. The Stage 5 contradictions return structured discrepancies for
the two demo scenarios:

  CODE-A: claim "we should mock the flaky test" → fact: inc_226 shows
          mocking this test caused a prod incident two weeks later

  SIMPLE-A: claim "incident-2026-04-09 is a new failure mode" → fact:
            inc_201 has the same root cause and an action item that was
            never implemented
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
        """Cross-check a memory claim against live entity records."""
        c = claim.lower()

        # CODE-A: any claim suggesting we mock the flaky test
        if "mock" in c and ("test" in c or "flaky" in c):
            inc = await self.query_entity("incident", "inc_226")
            return {
                "verified": False,
                "actual": {
                    "incident_id": inc["id"],
                    "endpoint": inc["endpoint"],
                    "summary": inc["summary"],
                    "fix_pr_url": inc["fix_pr_url"],
                },
                "discrepancy": (
                    "prior incident inc_226: mocking this test six months ago "
                    "caused a 14-minute production outage two weeks later"
                ),
            }

        # SIMPLE-A: claim that the new incident is novel
        if "incident" in c and ("rate" in c or "limiter" in c or "deploy" in c or "root cause" in c):
            inc = await self.query_entity("incident", "inc_201")
            return {
                "verified": False,
                "actual": {
                    "incident_id": inc["id"],
                    "endpoint": inc["endpoint"],
                    "summary": inc["summary"],
                    "root_cause": inc.get("root_cause", ""),
                },
                "discrepancy": (
                    "prior incident inc_201 (2026-02-14) had the same root cause; "
                    "action item AI-24 proposed a deploy validation gate but was never implemented"
                ),
            }

        return {"verified": True, "actual": {}, "discrepancy": ""}
