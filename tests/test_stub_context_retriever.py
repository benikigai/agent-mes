"""Tests for the StubContextRetriever choreographed stub."""

import pytest

from agent_mes.integrations.stubs.context_retriever import StubContextRetriever


@pytest.mark.asyncio
async def test_query_entity_service():
    ctx = StubContextRetriever()
    svc = await ctx.query_entity("service", "svc_auth")
    assert svc["name"] == "auth-service"
    assert svc["owner_team"] == "platform"


@pytest.mark.asyncio
async def test_query_entity_incident_inc_113():
    ctx = StubContextRetriever()
    inc = await ctx.query_entity("incident", "inc_113")
    assert inc["endpoint"] == "/v1/login"
    assert "rate limiter" in inc["summary"]


@pytest.mark.asyncio
async def test_list_related_incidents_for_auth():
    ctx = StubContextRetriever()
    incidents = await ctx.list_related("incident", {"service_id": "svc_auth"})
    assert len(incidents) >= 3
    assert any(i["id"] == "inc_113" for i in incidents)


@pytest.mark.asyncio
async def test_verify_claim_auth_rate_limit_drift():
    ctx = StubContextRetriever()
    result = await ctx.verify_claim(
        "auth rate limiter was fixed on the login service last month",
        entity_type="incident",
    )
    assert result["verified"] is False
    assert result["actual"]["endpoint"] == "/v1/login"
    assert "endpoint mismatch" in result["discrepancy"]
    assert "/v2/oauth" in result["discrepancy"]


@pytest.mark.asyncio
async def test_verify_claim_unrelated_returns_verified():
    ctx = StubContextRetriever()
    result = await ctx.verify_claim(
        "search service indexes documents nightly",
        entity_type="service",
    )
    assert result["verified"] is True
