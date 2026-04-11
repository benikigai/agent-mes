"""Tests for the demo fixtures (T9)."""

from agent_mes.demo.fake_slack import FAKE_SLACK, all_demo_tickets, get_fake_slack
from agent_mes.demo.poison_payload import POISON_DESTINATION, attempt_phone_home
from agent_mes.demo.seed_entities import (
    INCIDENTS,
    SERVICES,
    TICKETS,
    USERS,
    filter_entities,
    get_entity,
)
from agent_mes.demo.seed_memories import SEED_MEMORIES


def test_two_demo_tickets():
    assert all_demo_tickets() == ["TKT-001", "TKT-002"]
    assert len(FAKE_SLACK) == 2


def test_tkt_001_is_oauth_code():
    f = get_fake_slack("TKT-001")
    assert "oauth" in f["raw_text"].lower()
    assert "/v2" in f["raw_text"]
    assert "rate limit" in f["raw_text"].lower()
    assert f["plan_payload"]["blast_radius"]["network_egress"] is False
    assert len(f["plan_payload"]["acceptance_criteria"]) == 3


def test_tkt_002_is_status_email():
    f = get_fake_slack("TKT-002")
    assert "email" in f["raw_text"].lower()
    assert "status" in f["raw_text"].lower()
    assert f["plan_payload"]["blast_radius"]["network_egress"] is False


def test_seed_memories_has_adversary_claim():
    assert len(SEED_MEMORIES) == 10
    adversary = next(m for m in SEED_MEMORIES if "auth rate limiter" in m["text"] and "login service" in m["text"])
    assert adversary["confidence"] == 0.9
    assert "rate_limiter" in adversary["topics"]


def test_heliograph_schema_shape():
    assert len(SERVICES) == 4
    assert len(USERS) == 8
    assert len(INCIDENTS) == 12
    assert len(TICKETS) == 6


def test_inc_113_endpoint_is_v1_login():
    inc = get_entity("incident", "inc_113")
    assert inc["endpoint"] == "/v1/login"
    assert "rate limiter" in inc["summary"]


def test_tkt_982_body_mentions_v2_oauth():
    tkt = get_entity("ticket", "tkt_982")
    assert "/v2/oauth" in tkt["body"]
    assert tkt["service_id"] == "svc_auth"


def test_filter_incidents_by_service():
    auth_incs = filter_entities("incident", {"service_id": "svc_auth"})
    assert len(auth_incs) == 3  # inc_113, inc_104, inc_108
    endpoints = {i["endpoint"] for i in auth_incs}
    assert "/v1/login" in endpoints


def test_poison_payload_returns_violation():
    report = attempt_phone_home()
    assert report["destination"] == POISON_DESTINATION
    assert "BLAST_RADIUS_VIOLATION" in report["reason"]
    assert report["blocked_by"] == "blaxel_egress_monitor"
