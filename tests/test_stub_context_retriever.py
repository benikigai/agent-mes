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
async def test_query_entity_incident_inc_226_flaky_test_trap():
    ctx = StubContextRetriever()
    inc = await ctx.query_entity("incident", "inc_226")
    assert "test_oauth_token_refresh" in inc["summary"]
    assert "mocked" in inc["summary"].lower()


@pytest.mark.asyncio
async def test_list_related_incidents_for_auth():
    ctx = StubContextRetriever()
    incidents = await ctx.list_related("incident", {"service_id": "svc_auth"})
    assert any(i["id"] == "inc_226" for i in incidents)
    assert any(i["id"] == "inc_201" for i in incidents)
    assert any(i["id"] == "inc_311" for i in incidents)


@pytest.mark.asyncio
async def test_verify_claim_flaky_test_mock_drift():
    ctx = StubContextRetriever()
    result = await ctx.verify_claim(
        "the flaky test should be mocked for now",
        entity_type="incident",
    )
    assert result["verified"] is False
    assert result["actual"]["incident_id"] == "inc_226"
    assert "mocking" in result["discrepancy"].lower()


@pytest.mark.asyncio
async def test_verify_claim_postmortem_drift():
    ctx = StubContextRetriever()
    result = await ctx.verify_claim(
        "incident-2026-04-09 rate-limiter outage is a new root cause",
        entity_type="incident",
    )
    assert result["verified"] is False
    assert result["actual"]["incident_id"] == "inc_201"
    assert "ai-24" in result["discrepancy"].lower()


@pytest.mark.asyncio
async def test_verify_claim_unrelated_returns_verified():
    ctx = StubContextRetriever()
    result = await ctx.verify_claim(
        "search service indexes documents nightly",
        entity_type="service",
    )
    assert result["verified"] is True
