"""Heliograph fake company schema — fixtures for the StubContextRetriever.

Includes the structural contradiction the Stage 5 drift catch surfaces:
  - Incident inc_113 was a fix on /v1/login (the historical fact)
  - Ticket  tkt_982 is about /v2/oauth (the current task)

The agent retrieves the seed memory ("we already fixed it") and the Context
Retriever returns inc_113 with endpoint=/v1/login. The MISMATCH between the
incident's endpoint and the new ticket's endpoint is the demo gold moment.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

NOW = datetime.now()


def _days_ago_ts(days: int) -> float:
    return (NOW - timedelta(days=days)).timestamp()


# ─── Services ───────────────────────────────────────────────────────────────
SERVICES: list[dict[str, Any]] = [
    {
        "id": "svc_auth",
        "name": "auth-service",
        "owner_team": "platform",
        "repo_url": "https://github.com/heliograph/auth",
    },
    {
        "id": "svc_billing",
        "name": "billing-service",
        "owner_team": "growth",
        "repo_url": "https://github.com/heliograph/billing",
    },
    {
        "id": "svc_notify",
        "name": "notify-service",
        "owner_team": "platform",
        "repo_url": "https://github.com/heliograph/notify",
    },
    {
        "id": "svc_search",
        "name": "search-service",
        "owner_team": "data",
        "repo_url": "https://github.com/heliograph/search",
    },
]

# ─── Users ──────────────────────────────────────────────────────────────────
USERS: list[dict[str, Any]] = [
    {"id": "usr_sarah", "name": "Sarah Kim", "slack_handle": "sarah", "team": "platform"},
    {"id": "usr_marcus", "name": "Marcus Lee", "slack_handle": "marcus", "team": "growth"},
    {"id": "usr_jamie", "name": "Jamie Patel", "slack_handle": "jamie", "team": "platform"},
    {"id": "usr_ren", "name": "Ren Tanaka", "slack_handle": "ren", "team": "data"},
    {"id": "usr_priya", "name": "Priya Iyer", "slack_handle": "priya", "team": "growth"},
    {"id": "usr_alex", "name": "Alex Volkov", "slack_handle": "alex", "team": "platform"},
    {"id": "usr_dani", "name": "Dani Cruz", "slack_handle": "dani", "team": "data"},
    {"id": "usr_sam", "name": "Sam Reed", "slack_handle": "sam", "team": "platform"},
]

# ─── Incidents ──────────────────────────────────────────────────────────────
INCIDENTS: list[dict[str, Any]] = [
    # THE adversary incident: rate limiter fix on /v1/login (NOT /v2/oauth)
    {
        "id": "inc_113",
        "service_id": "svc_auth",
        "endpoint": "/v1/login",
        "summary": "auth rate limiter bumped 100→500rpm on login endpoint",
        "opened_at": _days_ago_ts(29),
        "resolved_at": _days_ago_ts(28),
        "fix_pr_url": "https://github.com/heliograph/auth/pull/447",
    },
    {
        "id": "inc_101",
        "service_id": "svc_billing",
        "endpoint": "/v1/charge",
        "summary": "stripe webhook timeout on retries",
        "opened_at": _days_ago_ts(60),
        "resolved_at": _days_ago_ts(59),
        "fix_pr_url": "https://github.com/heliograph/billing/pull/220",
    },
    {
        "id": "inc_102",
        "service_id": "svc_notify",
        "endpoint": "/v1/push",
        "summary": "APNs cert expired",
        "opened_at": _days_ago_ts(120),
        "resolved_at": _days_ago_ts(119),
        "fix_pr_url": "https://github.com/heliograph/notify/pull/88",
    },
    {
        "id": "inc_103",
        "service_id": "svc_search",
        "endpoint": "/v1/query",
        "summary": "elasticsearch heap pressure during reindex",
        "opened_at": _days_ago_ts(90),
        "resolved_at": _days_ago_ts(88),
        "fix_pr_url": "https://github.com/heliograph/search/pull/512",
    },
    {
        "id": "inc_104",
        "service_id": "svc_auth",
        "endpoint": "/v1/session",
        "summary": "session token leak in error response",
        "opened_at": _days_ago_ts(75),
        "resolved_at": _days_ago_ts(73),
        "fix_pr_url": "https://github.com/heliograph/auth/pull/401",
    },
    {
        "id": "inc_105",
        "service_id": "svc_billing",
        "endpoint": "/v1/invoice",
        "summary": "invoice rounding bug on currencies with no decimal",
        "opened_at": _days_ago_ts(50),
        "resolved_at": _days_ago_ts(49),
        "fix_pr_url": "https://github.com/heliograph/billing/pull/231",
    },
    {
        "id": "inc_106",
        "service_id": "svc_notify",
        "endpoint": "/v2/email",
        "summary": "SES rate limit exceeded during marketing send",
        "opened_at": _days_ago_ts(40),
        "resolved_at": _days_ago_ts(39),
        "fix_pr_url": "https://github.com/heliograph/notify/pull/95",
    },
    {
        "id": "inc_107",
        "service_id": "svc_search",
        "endpoint": "/v2/suggest",
        "summary": "autocomplete returning stale results after index swap",
        "opened_at": _days_ago_ts(20),
        "resolved_at": _days_ago_ts(19),
        "fix_pr_url": "https://github.com/heliograph/search/pull/520",
    },
    {
        "id": "inc_108",
        "service_id": "svc_auth",
        "endpoint": "/v1/sso",
        "summary": "okta SAML response signature validation regression",
        "opened_at": _days_ago_ts(15),
        "resolved_at": _days_ago_ts(14),
        "fix_pr_url": "https://github.com/heliograph/auth/pull/455",
    },
    {
        "id": "inc_109",
        "service_id": "svc_billing",
        "endpoint": "/v1/refund",
        "summary": "refund webhook fires twice when stripe retries",
        "opened_at": _days_ago_ts(8),
        "resolved_at": _days_ago_ts(7),
        "fix_pr_url": "https://github.com/heliograph/billing/pull/240",
    },
    {
        "id": "inc_110",
        "service_id": "svc_notify",
        "endpoint": "/v1/sms",
        "summary": "twilio number rotation broke status callbacks",
        "opened_at": _days_ago_ts(35),
        "resolved_at": _days_ago_ts(34),
        "fix_pr_url": "https://github.com/heliograph/notify/pull/100",
    },
    {
        "id": "inc_111",
        "service_id": "svc_search",
        "endpoint": "/v1/query",
        "summary": "query parser crash on unicode normalization edge case",
        "opened_at": _days_ago_ts(5),
        "resolved_at": _days_ago_ts(4),
        "fix_pr_url": "https://github.com/heliograph/search/pull/525",
    },
]

# ─── Tickets ────────────────────────────────────────────────────────────────
TICKETS: list[dict[str, Any]] = [
    # THE current ticket — about /v2/oauth (different endpoint than inc_113)
    {
        "id": "tkt_982",
        "requester_id": "usr_sarah",
        "service_id": "svc_auth",
        "priority": "P2",
        "status": "open",
        "body": "rate-limiting on /v2/oauth too strict — customers reporting 429s on token refresh",
    },
    {
        "id": "tkt_950",
        "requester_id": "usr_marcus",
        "service_id": "svc_billing",
        "priority": "P3",
        "status": "open",
        "body": "incorrect tax calculation on EU invoices",
    },
    {
        "id": "tkt_961",
        "requester_id": "usr_jamie",
        "service_id": "svc_notify",
        "priority": "P3",
        "status": "in_progress",
        "body": "push notifications not arriving on iOS 18",
    },
    {
        "id": "tkt_973",
        "requester_id": "usr_ren",
        "service_id": "svc_search",
        "priority": "P4",
        "status": "open",
        "body": "search ranking weights need to favor recency for blog content",
    },
    {
        "id": "tkt_980",
        "requester_id": "usr_priya",
        "service_id": "svc_auth",
        "priority": "P3",
        "status": "open",
        "body": "MFA SMS codes occasionally arrive after the 60s expiration",
    },
    {
        "id": "tkt_981",
        "requester_id": "usr_alex",
        "service_id": "svc_billing",
        "priority": "P4",
        "status": "open",
        "body": "annual plan discount not applied when upgrading mid-cycle",
    },
]


def get_entity(entity_type: str, entity_id: str) -> dict[str, Any]:
    """Lookup helper used by the StubContextRetriever."""
    table = {
        "service": SERVICES,
        "user": USERS,
        "incident": INCIDENTS,
        "ticket": TICKETS,
    }[entity_type]
    for entry in table:
        if entry["id"] == entity_id:
            return entry
    raise KeyError(f"{entity_type} {entity_id} not found")


def filter_entities(entity_type: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter helper used by the StubContextRetriever."""
    table = {
        "service": SERVICES,
        "user": USERS,
        "incident": INCIDENTS,
        "ticket": TICKETS,
    }[entity_type]
    return [e for e in table if all(e.get(k) == v for k, v in filters.items())]
