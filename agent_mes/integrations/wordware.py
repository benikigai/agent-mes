"""Wordware planner with stub mode (default) and real mode placeholder.

Stub mode returns hardcoded MESTask first-stage payloads from
agent_mes.demo.fake_slack — same beats every demo. Real mode POSTs to
a deployed WordApp flow URL when one exists (post-MVP additive task).
"""

from __future__ import annotations

from typing import Any, Literal

import httpx

from agent_mes.demo.fake_slack import FAKE_SLACK


class WordwarePlanner:
    """Implements WordwarePlannerProtocol — stub by default."""

    def __init__(
        self,
        mode: Literal["stub", "real"] = "stub",
        flow_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.mode = mode
        self.flow_url = flow_url
        self.api_key = api_key

    async def plan_from_slack(
        self, raw_text: str, requester: str, channel: str
    ) -> dict[str, Any]:
        if self.mode == "stub":
            return self._stub_plan(raw_text, requester, channel)
        return await self._real_plan(raw_text, requester, channel)

    def _stub_plan(self, raw_text: str, requester: str, channel: str) -> dict[str, Any]:
        """Match the raw_text against a known fixture; fall back to TKT-001."""
        for ticket_id, fixture in FAKE_SLACK.items():
            if (
                fixture["raw_text"] == raw_text
                or fixture["requester"] == requester
            ):
                return fixture["plan_payload"]
        # Fall back to the first fixture so the demo never crashes
        return FAKE_SLACK["TKT-001"]["plan_payload"]

    async def _real_plan(
        self, raw_text: str, requester: str, channel: str
    ) -> dict[str, Any]:
        """POST to a real WordApp flow. Used after H7 if a flow is built."""
        if not self.flow_url:
            raise RuntimeError(
                "WordwarePlanner mode='real' requires flow_url"
            )
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self.flow_url,
                json={
                    "inputs": {
                        "slack_text": raw_text,
                        "requester": requester,
                        "channel": channel,
                    }
                },
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
