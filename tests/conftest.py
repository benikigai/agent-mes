"""Shared pytest fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the module-level rate limiter before each test.

    The limiter persists across tests, and TestClient requests without a
    CF-Connecting-IP header all share one key — so without this reset one
    test's mutation calls could spuriously 429 a later test. Imported lazily
    so non-web tests don't pull in the FastAPI app.
    """
    from agent_mes.web import server

    server._rate_limiter._hits.clear()
    yield
