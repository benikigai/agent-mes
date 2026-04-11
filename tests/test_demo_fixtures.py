"""Tests for the demo fixtures (T9) — flaky test + postmortem scenarios."""

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


def test_tkt_001_is_flaky_test_code():
    f = get_fake_slack("TKT-001")
    assert "flaky" in f["raw_text"].lower()
    assert "test_oauth_token_refresh" in f["raw_text"]
    assert "race" in f["raw_text"].lower() or "timing" in f["raw_text"].lower()
    assert f["plan_payload"]["blast_radius"]["network_egress"] is False
    assert len(f["plan_payload"]["acceptance_criteria"]) == 3
    assert "distributed lock" not in f["raw_text"]  # the lock is the FIX, not the prompt


def test_tkt_002_is_postmortem_simple():
    f = get_fake_slack("TKT-002")
    assert "postmortem" in f["raw_text"].lower()
    assert "incident-2026-04-09" in f["raw_text"]
    assert "5 whys" in f["raw_text"].lower() or "root cause" in f["raw_text"].lower()
    assert f["plan_payload"]["blast_radius"]["network_egress"] is False


def test_seed_memories_has_both_adversaries():
    assert len(SEED_MEMORIES) == 10
    code_adv = next(m for m in SEED_MEMORIES if m["id"] == "mem_0001")
    assert "mocked" in code_adv["text"].lower()
    assert "prod incident" in code_adv["text"].lower()

    simple_adv = next(m for m in SEED_MEMORIES if m["id"] == "mem_0002")
    assert "incident-2026-02-14" in simple_adv["text"]
    assert "rate-limiter" in simple_adv["text"]
    assert "ai-24" in simple_adv["text"].lower()


def test_heliograph_schema_shape():
    assert len(SERVICES) == 4
    assert len(USERS) == 8
    assert len(INCIDENTS) == 12
    assert len(TICKETS) == 6


def test_inc_226_is_the_code_a_trap():
    inc = get_entity("incident", "inc_226")
    assert "mocked" in inc["summary"].lower()
    assert "test_oauth_token_refresh" in inc["summary"]
    assert "prod" in inc["summary"].lower()


def test_inc_201_is_the_simple_a_trap():
    inc = get_entity("incident", "inc_201")
    assert "rate-limiter" in inc["summary"].lower()
    assert "ai-24" in inc["summary"].lower()
    assert "never implemented" in inc["summary"].lower()


def test_inc_311_is_the_current_postmortem_subject():
    inc = get_entity("incident", "inc_311")
    assert "2026-04-09" in inc["summary"]
    assert "rate-limiter" in inc["summary"].lower()
    # Same root cause as inc_201
    assert inc["root_cause"] == get_entity("incident", "inc_201")["root_cause"]


def test_filter_incidents_by_service():
    auth_incs = filter_entities("incident", {"service_id": "svc_auth"})
    assert len(auth_incs) >= 5  # 226, 201, 311, 104, 108
    ids = {i["id"] for i in auth_incs}
    assert {"inc_226", "inc_201", "inc_311"}.issubset(ids)


def test_poison_payload_returns_violation():
    report = attempt_phone_home()
    assert report["destination"] == POISON_DESTINATION
    assert "BLAST_RADIUS_VIOLATION" in report["reason"]
    assert report["blocked_by"] == "blaxel_egress_monitor"
