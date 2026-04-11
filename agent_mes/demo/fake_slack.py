"""Fake Slack messages used as Plan stage input fixtures.

Two demo tickets:
- TKT-001 (CODE)   : OAuth /v2 rate-limit fix that triggers the Stage 5 memory drift catch
- TKT-002 (SIMPLE) : status update email about a recent incident

Each entry maps a ticket id to:
  raw_text       — the inbound message (what Wordware would compile)
  requester      — slack handle
  channel        — slack channel
  plan_payload   — what the Wordware stub returns from plan_from_slack
                   (matches the dict-shape WordwarePlannerProtocol.plan_from_slack returns)
"""

from __future__ import annotations

from typing import Any

FAKE_SLACK: dict[str, dict[str, Any]] = {
    "TKT-001": {
        "raw_text": (
            "hey can someone fix the oauth rate limit on /v2 — "
            "customers are getting 429s on token refresh and the "
            "/v2/oauth endpoint is way too aggressive. needs to be like /v1/login was."
        ),
        "requester": "sarah",
        "channel": "#bugs",
        "plan_payload": {
            "intent": "raise the OAuth /v2 rate limit so token refresh stops 429ing",
            "acceptance_criteria": [
                {
                    "description": "rate limit on /v2/oauth raised to at least 500rpm",
                    "machine_check": "pytest tests/auth/test_rate_limit.py -k oauth_v2",
                },
                {
                    "description": "no regression on /v1/login rate limit",
                    "machine_check": "pytest tests/auth/test_rate_limit.py -k login_v1",
                },
                {
                    "description": "no outbound network calls",
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
    "TKT-002": {
        "raw_text": (
            "send a status update email to the team about the auth incident "
            "from last night — keep it short, mention root cause + ETA, "
            "use a calm tone."
        ),
        "requester": "marcus",
        "channel": "#announcements",
        "plan_payload": {
            "intent": "draft a status-update email about the recent auth incident",
            "acceptance_criteria": [
                {
                    "description": "email body under 200 words",
                    "machine_check": "wc -w drafts/email-TKT-002.md",
                },
                {
                    "description": "tone is calm and informative",
                    "machine_check": "agent-mes review tone drafts/email-TKT-002.md",
                },
            ],
            "blast_radius": {
                "allowed_paths": ["drafts/", ".demo/outputs/"],
                "network_egress": False,
                "max_cost_usd": 0.05,
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
