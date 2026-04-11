"""Heliograph fake company schema — fixtures for the StubContextRetriever.

Includes the two structural facts the Stage 5 drift catches surface:

  CODE-A trap: incident-2025-10-12 (six months ago) — record of the prior
  flaky-test-mocking incident where mocking caused a prod failure two
  weeks later. inc_226's fix_pr_url is the prior PR that mocked the test.

  SIMPLE-A trap: incident-2026-02-14 — record of the prior incident with
  the SAME root cause as inc_311 (the current incident-2026-04-09). Action
  item AI-24 from inc_201 was "add deploy-pipeline validation gate" — never
  implemented. The postmortem agent retrieves both incidents and the
  Context Retriever flags the duplicate root cause.
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
    # ── ADVERSARY incidents (the demo gold) ──
    # CODE-A trap: prior flaky-test mocking incident (6 months ago)
    {
        "id": "inc_226",
        "service_id": "svc_auth",
        "endpoint": "/v1/oauth/refresh",
        "summary": "test_oauth_token_refresh was mocked instead of fixed; race condition fired in prod 2 weeks later, ~14min outage during refresh storm",
        "opened_at": _days_ago_ts(180),
        "resolved_at": _days_ago_ts(166),
        "fix_pr_url": "https://github.com/heliograph/auth/pull/389",
        "root_cause": "race condition in token refresh path; was masked by a test mock instead of fixed",
    },
    # SIMPLE-A trap: prior outage with same root cause as the current incident
    {
        "id": "inc_201",
        "service_id": "svc_auth",
        "endpoint": "/v1/login",
        "summary": "auth-service down 18min — rate-limiter misconfig from deploy pipeline; action item AI-24 proposed deploy validation gate, never implemented",
        "opened_at": _days_ago_ts(57),
        "resolved_at": _days_ago_ts(57),
        "fix_pr_url": "https://github.com/heliograph/auth/pull/431",
        "root_cause": "rate-limiter misconfig propagated through deploy pipeline; no validation gate caught it",
    },
    # SIMPLE-A subject: the current incident being post-mortemed
    {
        "id": "inc_311",
        "service_id": "svc_auth",
        "endpoint": "/v1/login",
        "summary": "auth-service down 28min on 2026-04-09 14:30 PDT — rate-limiter misconfig from morning deploy; same root cause as inc_201",
        "opened_at": _days_ago_ts(2),
        "resolved_at": _days_ago_ts(2),
        "fix_pr_url": "https://github.com/heliograph/auth/pull/467",
        "root_cause": "rate-limiter misconfig propagated through deploy pipeline; no validation gate caught it",
    },
    # ── Filler incidents ──
    {
        "id": "inc_101",
        "service_id": "svc_billing",
        "endpoint": "/v1/charge",
        "summary": "stripe webhook timeout on retries",
        "opened_at": _days_ago_ts(60),
        "resolved_at": _days_ago_ts(59),
        "fix_pr_url": "https://github.com/heliograph/billing/pull/220",
        "root_cause": "exponential backoff misconfigured",
    },
    {
        "id": "inc_102",
        "service_id": "svc_notify",
        "endpoint": "/v1/push",
        "summary": "APNs cert expired",
        "opened_at": _days_ago_ts(120),
        "resolved_at": _days_ago_ts(119),
        "fix_pr_url": "https://github.com/heliograph/notify/pull/88",
        "root_cause": "cert renewal cron failed silently",
    },
    {
        "id": "inc_103",
        "service_id": "svc_search",
        "endpoint": "/v1/query",
        "summary": "elasticsearch heap pressure during reindex",
        "opened_at": _days_ago_ts(90),
        "resolved_at": _days_ago_ts(88),
        "fix_pr_url": "https://github.com/heliograph/search/pull/512",
        "root_cause": "reindex job not throttled",
    },
    {
        "id": "inc_104",
        "service_id": "svc_auth",
        "endpoint": "/v1/session",
        "summary": "session token leak in error response",
        "opened_at": _days_ago_ts(75),
        "resolved_at": _days_ago_ts(73),
        "fix_pr_url": "https://github.com/heliograph/auth/pull/401",
        "root_cause": "error handler logged tokens",
    },
    {
        "id": "inc_105",
        "service_id": "svc_billing",
        "endpoint": "/v1/invoice",
        "summary": "invoice rounding bug on currencies with no decimal",
        "opened_at": _days_ago_ts(50),
        "resolved_at": _days_ago_ts(49),
        "fix_pr_url": "https://github.com/heliograph/billing/pull/231",
        "root_cause": "decimal handling assumed 2 places",
    },
    {
        "id": "inc_106",
        "service_id": "svc_notify",
        "endpoint": "/v2/email",
        "summary": "SES rate limit exceeded during marketing send",
        "opened_at": _days_ago_ts(40),
        "resolved_at": _days_ago_ts(39),
        "fix_pr_url": "https://github.com/heliograph/notify/pull/95",
        "root_cause": "no batching on marketing path",
    },
    {
        "id": "inc_107",
        "service_id": "svc_search",
        "endpoint": "/v2/suggest",
        "summary": "autocomplete returning stale results after index swap",
        "opened_at": _days_ago_ts(20),
        "resolved_at": _days_ago_ts(19),
        "fix_pr_url": "https://github.com/heliograph/search/pull/520",
        "root_cause": "index swap forgot to bump cache version",
    },
    {
        "id": "inc_108",
        "service_id": "svc_auth",
        "endpoint": "/v1/sso",
        "summary": "okta SAML signature validation regression",
        "opened_at": _days_ago_ts(15),
        "resolved_at": _days_ago_ts(14),
        "fix_pr_url": "https://github.com/heliograph/auth/pull/455",
        "root_cause": "library upgrade dropped a default flag",
    },
    {
        "id": "inc_109",
        "service_id": "svc_billing",
        "endpoint": "/v1/refund",
        "summary": "refund webhook fires twice when stripe retries",
        "opened_at": _days_ago_ts(8),
        "resolved_at": _days_ago_ts(7),
        "fix_pr_url": "https://github.com/heliograph/billing/pull/240",
        "root_cause": "missing idempotency key check",
    },
]

# ─── Tickets ────────────────────────────────────────────────────────────────
TICKETS: list[dict[str, Any]] = [
    {
        "id": "tkt_982",
        "requester_id": "usr_sarah",
        "service_id": "svc_auth",
        "priority": "P2",
        "status": "open",
        "body": "test_oauth_token_refresh is flaky on CI — failing ~10% with timing issues",
    },
    {
        "id": "tkt_983",
        "requester_id": "usr_marcus",
        "service_id": "svc_auth",
        "priority": "P1",
        "status": "open",
        "body": "draft postmortem for incident-2026-04-09 (auth-service rate-limiter outage)",
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
