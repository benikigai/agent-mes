"""Plain-Redis backend for the /redis dashboard.

Uses vanilla SET/GET/SCAN instead of RedisJSON so a bare
``brew install redis`` is enough — no Redis Stack required. Plushpalace
entities are serialized as JSON strings under ``{type}:{id}`` keys.

``seed_plushpalace`` loads all YAML entities from ~/code/plushpalace-world
and bulk-writes them. ``connect_or_none`` returns a client if Redis is
reachable; everything else in the server treats ``None`` as "offline,
fall back to plushpalace stub store".
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_REDIS_URL = "redis://localhost:6379"

# Per-entity primary key field — plushpalace models use different names.
# Default ``id`` is correct for most, but several need an override.
_ID_FIELDS: dict[str, str] = {
    "product": "sku",
    "repository": "name",
    "code_change": "title",
    "vendor": "id",
    "person": "id",
    "customer": "id",
    "incident": "id",
    "postmortem": "id",
    "email": "id",
    "lesson": "id",
}


def _entity_id(kind: str, doc: dict[str, Any]) -> str:
    """Extract the primary key for a plushpalace entity dict."""
    field = _ID_FIELDS.get(kind, "id")
    val = doc.get(field) or doc.get("id") or doc.get("name") or doc.get("title")
    if not val:
        return "unknown"
    # Flatten to a dns-label-ish slug so it's safe in a Redis key
    s = str(val).strip().lower().replace(" ", "-")
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in s)[:80] or "unknown"


def connect_or_none(url: str | None = None):
    """Return a redis.Redis client if the URL is reachable, else None."""
    try:
        import redis

        u = url or os.environ.get("AGENTMES_REDIS_URL") or DEFAULT_REDIS_URL
        client = redis.Redis.from_url(
            u, decode_responses=True, socket_connect_timeout=1.0
        )
        client.ping()
        return client
    except Exception:  # noqa: BLE001
        return None


def _load_plushpalace_dicts() -> dict[str, list[dict[str, Any]]]:
    try:
        from plushpalace.loader import load_all

        data_dir = Path.home() / "code" / "plushpalace-world" / "data"
        if not data_dir.exists():
            return {}
        raw = load_all(data_dir)
        out: dict[str, list[dict[str, Any]]] = {}
        for kind, entities in raw.items():
            out[kind] = []
            for e in entities:
                if hasattr(e, "model_dump"):
                    out[kind].append(e.model_dump(mode="json"))
                else:
                    out[kind].append(dict(e.__dict__))
        return out
    except Exception:  # noqa: BLE001
        return {}


def seed_plushpalace(client, flush: bool = True) -> dict[str, int]:
    """Load plushpalace YAML and bulk-write every entity into Redis as a
    JSON string under ``{kind}:{id}``. Returns a per-type count dict."""
    data = _load_plushpalace_dicts()
    if flush:
        client.flushdb()
    counts: dict[str, int] = {}
    pipe = client.pipeline(transaction=False)
    for kind, docs in data.items():
        for doc in docs:
            eid = _entity_id(kind, doc)
            key = f"{kind}:{eid}"
            pipe.set(key, json.dumps(doc, default=str))
        counts[kind] = len(docs)
    pipe.execute()
    return counts


def scan_all_keys(client) -> list[str]:
    """Return every key in Redis, sorted by type-then-id."""
    keys: list[str] = []
    cursor = 0
    while True:
        cursor, batch = client.scan(cursor=cursor, count=500)
        keys.extend(batch)
        if cursor == 0:
            break
    return sorted(keys)


def get_value(client, key: str) -> dict[str, Any] | None:
    raw = client.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {"_raw": raw}


def group_by_type(keys: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for k in keys:
        kind, _, _ = k.partition(":")
        grouped.setdefault(kind, []).append(k)
    return grouped
