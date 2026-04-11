"""Fake Slack messages used as Plan stage input fixtures.

Two demo tickets — both wired to land Redis Memory drift catches at Stage 5:

- TKT-001 (CODE)   : flaky test fix that triggers a "we mocked it before" recall
- TKT-002 (SIMPLE) : postmortem draft that triggers a "we've put out this fire before" recall

Each entry maps a ticket id to:
  raw_text       — the inbound message (what Wordware compiles)
  requester      — slack handle
  channel        — slack channel
  plan_payload   — what the Wordware stub returns from plan_from_slack
"""

from __future__ import annotations

from typing import Any

FAKE_SLACK: dict[str, dict[str, Any]] = {
    # ── CODE-A: Fix flaky test that blocks CI ────────────────────────────
    "TKT-001": {
        "raw_text": (
            "fix the flaky test test_oauth_token_refresh — it's been failing ~10% "
            "of the time on CI for a week and blocking every PR. timing/race "
            "condition somewhere in the refresh flow. needs a real fix not a mock."
        ),
        "requester": "sarah",
        "channel": "#bugs",
        "plan_payload": {
            "intent": "fix the flaky test test_oauth_token_refresh by addressing the underlying race condition",
            "acceptance_criteria": [
                {
                    "description": "test passes 100 times in a row in the sandbox",
                    "machine_check": "pytest tests/auth/test_oauth_token_refresh.py --count=100",
                },
                {
                    "description": "fix touches the production code, not the test mock",
                    "machine_check": "pytest tests/auth/test_oauth_token_refresh.py -k 'not mocked'",
                },
                {
                    "description": "no outbound network calls during the test",
                    "machine_check": "pytest tests/auth/test_isolation.py",
                },
            ],
            "blast_radius": {
                "allowed_paths": ["auth/", "tests/auth/"],
                "network_egress": False,
                "max_cost_usd": 0.50,
            },
        },
    },
    # ── SIMPLE-A: Draft postmortem for last week's outage ────────────────
    "TKT-002": {
        "raw_text": (
            "draft a postmortem for incident-2026-04-09 — auth-service went down "
            "at 14:30 PDT for ~28 minutes. customers couldn't log in. root cause "
            "looks like the rate-limiter misconfig from the deploy that morning. "
            "need timeline, 5 whys, action items with owners + due dates."
        ),
        "requester": "marcus",
        "channel": "#incidents",
        "plan_payload": {
            "intent": "draft postmortem for incident-2026-04-09 covering root cause, timeline, 5 whys, and action items",
            "acceptance_criteria": [
                {
                    "description": "every action item has an owner and a due date",
                    "machine_check": "agent-mes lint postmortem .demo/outputs/postmortem-TKT-002.md",
                },
                {
                    "description": "no PII in customer-facing sections",
                    "machine_check": "agent-mes scrub-pii .demo/outputs/postmortem-TKT-002.md",
                },
                {
                    "description": "5 whys section has at least 5 levels",
                    "machine_check": "grep -c '^Why' .demo/outputs/postmortem-TKT-002.md",
                },
            ],
            "blast_radius": {
                "allowed_paths": ["drafts/", ".demo/outputs/"],
                "network_egress": False,
                "max_cost_usd": 0.10,
            },
        },
    },
}


def get_fake_slack(ticket_id: str) -> dict[str, Any]:
    """Return the fake Slack fixture for the given ticket id."""
    return FAKE_SLACK[ticket_id]


def all_demo_tickets() -> list[str]:
    """Return ticket ids in demo order."""
    return ["TKT-001", "TKT-002"]
