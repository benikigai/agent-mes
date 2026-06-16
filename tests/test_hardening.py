"""Phase-1 hardening tests — the invariants that would have caught the live
divergences: /api/mode lying about wiring, the unbounded SSE amplifier, and
unthrottled mutation endpoints.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from agent_mes.integrations.stubs.blaxel import StubBlaxelVerifier
from agent_mes.stages.test import TestStage
from agent_mes.web import server
from agent_mes.web.events import (
    MAX_SUBSCRIBERS,
    MAX_SUBSCRIBERS_PER_KEY,
    QUEUE_MAXSIZE,
    EventBroker,
    SubscriberLimitExceeded,
)

client = TestClient(server.app)


# ─── /api/mode honesty: the badge must match the actual wiring ───────────────


def test_mode_matches_wiring():
    """/api/mode.blaxel_live must equal what _build_pipeline actually builds.

    The old probe imported our wrapper module (which lazy-imports the SDK),
    so the badge claimed blaxel_live:true while TestStage ran the stub. This
    pins the badge to the real verifier instance.
    """
    mode = client.get("/api/mode").json()
    pipeline = server._build_pipeline(server.state, "TKT-001")
    test_stage = next(s for s in pipeline.stages if isinstance(s, TestStage))
    verifier_is_stub = isinstance(test_stage.blaxel, StubBlaxelVerifier)
    # If the badge says live, the wiring must NOT be the stub, and vice-versa.
    assert mode["blaxel_live"] == (not verifier_is_stub), (
        f"badge blaxel_live={mode['blaxel_live']} but verifier is "
        f"{type(test_stage.blaxel).__name__}"
    )


def test_mode_blaxel_live_requires_real_sdk():
    """The flag tracks real SDK importability, not wrapper-module import."""
    sdk_importable = True
    try:
        import blaxel.core  # noqa: F401
    except Exception:  # noqa: BLE001
        sdk_importable = False
    expected = sdk_importable and server.os.environ.get("AGENTMES_BLAXEL_STUB") != "1"
    assert client.get("/api/mode").json()["blaxel_live"] == expected


# ─── SSE caps ────────────────────────────────────────────────────────────────


def test_subscribe_refuses_past_global_capacity():
    broker = EventBroker()
    # Distinct keys so we hit the GLOBAL cap, not the per-visitor cap.
    queues = [broker.subscribe(key=f"ip-{i}") for i in range(MAX_SUBSCRIBERS)]
    assert broker.subscriber_count == MAX_SUBSCRIBERS
    with pytest.raises(SubscriberLimitExceeded):
        broker.subscribe(key="one-more")
    # Freeing one slot lets a new connection in.
    broker.unsubscribe(queues[0])
    assert broker.subscribe(key="late") is not None


def test_per_visitor_subscriber_cap():
    """One visitor can't monopolize all the SSE slots and 503 everyone."""
    broker = EventBroker()
    mine = [broker.subscribe(key="1.2.3.4") for _ in range(MAX_SUBSCRIBERS_PER_KEY)]
    with pytest.raises(SubscriberLimitExceeded):
        broker.subscribe(key="1.2.3.4")
    # A different visitor is unaffected.
    assert broker.subscribe(key="5.6.7.8") is not None
    # Disconnecting frees that visitor's quota and decrements the per-key count.
    broker.unsubscribe(mine[0])
    assert broker.subscribe(key="1.2.3.4") is not None


def test_fanout_drops_oldest_never_blocks():
    """A slow consumer's queue stays bounded and keeps the NEWEST events."""
    broker = EventBroker()
    q = broker.subscribe()
    # Overflow the queue well past capacity without ever awaiting a consumer.
    for i in range(QUEUE_MAXSIZE + 50):
        broker.broadcast({"n": i})
    assert q.qsize() == QUEUE_MAXSIZE, "queue must stay bounded at maxsize"
    # Oldest were dropped; the most recent event is retained.
    drained = [q.get_nowait() for _ in range(q.qsize())]
    assert drained[-1] == {"n": QUEUE_MAXSIZE + 49}
    assert drained[0]["n"] >= 50  # the first 50 were dropped


def test_fanout_isolates_slow_from_fast_consumer():
    """One stuck client doesn't cost a healthy client any events."""
    broker = EventBroker()
    slow = broker.subscribe()  # never drained
    fast = broker.subscribe()
    for i in range(QUEUE_MAXSIZE + 10):
        broker.broadcast({"n": i})
        fast.get_nowait()  # fast keeps up
    assert slow.qsize() == QUEUE_MAXSIZE  # bounded
    assert fast.qsize() == 0  # fully consumed, lost nothing


# ─── rate limiting ───────────────────────────────────────────────────────────


def test_rate_limiter_sliding_window():
    rl = server.RateLimiter(max_events=3, window_s=10.0)
    assert rl.allow("ip-a", now=100.0)
    assert rl.allow("ip-a", now=101.0)
    assert rl.allow("ip-a", now=102.0)
    assert not rl.allow("ip-a", now=103.0)  # 4th in window → blocked
    # A different key is unaffected.
    assert rl.allow("ip-b", now=103.0)
    # Once the window slides past the early hits, the key recovers.
    assert rl.allow("ip-a", now=111.0)


def test_mutation_endpoint_429s_on_flood():
    """A flood of mutations from one visitor 429s. (Per-key isolation itself is
    covered by test_rate_limiter_sliding_window — TestClient shares one peer.)"""
    server.state.reset()
    saw_429 = False
    for _ in range(server.RATE_LIMIT_MAX + 5):
        if client.post("/api/reset").status_code == 429:
            saw_429 = True
            break
    assert saw_429, "expected a 429 once the per-visitor budget was exceeded"


def _fake_request(headers: dict, host: str = "127.0.0.1"):
    class _Req:
        def __init__(self):
            self.headers = headers

            class _C:
                pass

            c = _C()
            c.host = host
            self.client = c

    return _Req()


def test_client_key_trusts_forwarding_headers_only_from_loopback():
    # Through the tunnel/tailscale-serve the peer is loopback → headers trusted.
    assert server._client_key(_fake_request({"cf-connecting-ip": "1.2.3.4"})) == "1.2.3.4"
    assert (
        server._client_key(_fake_request({"x-forwarded-for": "5.6.7.8, 9.9.9.9"}))
        == "5.6.7.8"
    )
    assert server._client_key(_fake_request({})) == "127.0.0.1"
    # A direct (non-loopback) client cannot spoof its way to a fresh key —
    # the header is ignored and we fall back to the real peer address.
    assert (
        server._client_key(_fake_request({"cf-connecting-ip": "1.2.3.4"}, host="9.9.9.9"))
        == "9.9.9.9"
    )
