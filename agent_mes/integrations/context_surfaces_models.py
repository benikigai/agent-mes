"""Redis Context Surfaces data models for AgentMES ground truth.

Mirrors the shape of ``agent_mes/demo/seed_entities.py`` so a real
Redis Context Surfaces surface can serve the same facts the current
``StubContextRetriever`` serves. The two Stage-5 drift catches key off
the ``Incident`` model:

- CODE-A trap (TKT-001): looks up ``/v1/oauth/refresh`` incidents and
  flags ``inc_226`` as the prior "mocked instead of fixed" outage
- SIMPLE-A trap (TKT-002): finds ``/v1/login`` incidents whose
  ``root_cause`` matches and flags ``inc_201`` as a duplicate whose
  action item (AI-24, deploy validation gate) was never implemented

Create the surface with::

    ctxctl surface create \\
        --name "agentmes-ground-truth" \\
        --models agent_mes/integrations/context_surfaces_models.py \\
        --redis-addr "$REDIS_CTX_ADDR" \\
        --redis-password "$REDIS_CTX_PASSWORD" \\
        --admin-key "$CTX_ADMIN_KEY"

Seeding the surface with the fixture rows from ``seed_entities.py`` is a
separate follow-up — the ``ctxctl`` CLI handles surface definition only.
"""

from __future__ import annotations

from typing import Any

from context_surfaces.context_model import (
    ContextField,
    ContextModel,
    ContextRelationship,
)


# ─── Service ────────────────────────────────────────────────────────────────


class Service(ContextModel):
    """A backend service owned by a team (e.g. auth-service, billing-service)."""

    __redis_key_template__ = "service:{id}"

    id: str = ContextField(
        description="Service ID (e.g. svc_auth)",
        is_key_component=True,
    )
    name: str = ContextField(
        description="Human-readable service name",
        index="text",
        weight=2.0,
    )
    owner_team: str = ContextField(
        description="Team owning this service (platform, growth, data)",
        index="tag",
    )
    repo_url: str = ContextField(
        description="GitHub repo URL for this service",
    )

    # Relationships — each points back via the FK field on the other side.
    incidents: Any = ContextRelationship(
        description="All incidents that affected this service",
        source_field="service_id",
    )
    tickets: Any = ContextRelationship(
        description="All tickets filed against this service",
        source_field="service_id",
    )


# ─── User ───────────────────────────────────────────────────────────────────


class User(ContextModel):
    """An employee — Slack handle is the primary join key into ticket requesters."""

    __redis_key_template__ = "user:{id}"

    id: str = ContextField(
        description="User ID (e.g. usr_sarah)",
        is_key_component=True,
    )
    name: str = ContextField(
        description="Full name",
        index="text",
    )
    slack_handle: str = ContextField(
        description="Slack handle without the @ prefix (e.g. sarah)",
        index="tag",
        no_stem=True,
    )
    team: str = ContextField(
        description="Team (platform, growth, data)",
        index="tag",
    )

    tickets: Any = ContextRelationship(
        description="Tickets this user has filed",
        source_field="requester_id",
    )


# ─── Incident — the Stage-5 drift-catch gold ───────────────────────────────


class Incident(ContextModel):
    """Historical production incident.

    The Stage-5 Review drift catches semantic-search ``root_cause`` and
    ``summary`` against the current task's inferred root cause. When a
    prior incident matches, the Review stage raises a HumanGate so the
    operator can confirm whether the fix is a duplicate of a known one.
    """

    __redis_key_template__ = "incident:{id}"

    id: str = ContextField(
        description="Incident ID (e.g. inc_201)",
        is_key_component=True,
    )
    service_id: str = ContextField(
        description="FK to the Service that experienced the incident",
        index="tag",
    )
    endpoint: str = ContextField(
        description="API endpoint path involved (e.g. /v1/login, /v1/oauth/refresh)",
        index="text",
        no_stem=True,
    )
    summary: str = ContextField(
        description="One-paragraph narrative of what happened, blast radius, and why",
        index="text",
        weight=1.5,
    )
    opened_at: float = ContextField(
        description="Unix timestamp when the incident was opened",
        index="numeric",
        sortable=True,
    )
    resolved_at: float = ContextField(
        description="Unix timestamp when the incident was resolved",
        index="numeric",
        sortable=True,
    )
    fix_pr_url: str = ContextField(
        description="URL of the PR that shipped the fix",
    )
    root_cause: str = ContextField(
        description="Root cause description — the field the déjà-vu detector searches",
        index="text",
        weight=2.0,
    )

    service: Any = ContextRelationship(
        description="The service this incident affected",
        source_field="service_id",
    )


# ─── Ticket ─────────────────────────────────────────────────────────────────


class Ticket(ContextModel):
    """Engineering ticket filed by a user against a service."""

    __redis_key_template__ = "ticket:{id}"

    id: str = ContextField(
        description="Ticket ID (e.g. tkt_982)",
        is_key_component=True,
    )
    requester_id: str = ContextField(
        description="FK to the User who filed the ticket",
        index="tag",
    )
    service_id: str = ContextField(
        description="FK to the Service this ticket is filed against",
        index="tag",
    )
    priority: str = ContextField(
        description="Ticket priority (P1, P2, P3, P4)",
        index="tag",
    )
    status: str = ContextField(
        description="Ticket status (open, in_progress, closed)",
        index="tag",
    )
    body: str = ContextField(
        description="The ticket body — primary semantic search field for Plan stage",
        index="text",
        weight=1.5,
    )

    requester: Any = ContextRelationship(
        description="The user who filed the ticket",
        source_field="requester_id",
    )
    service: Any = ContextRelationship(
        description="The service this ticket is filed against",
        source_field="service_id",
    )
