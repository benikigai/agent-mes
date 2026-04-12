"""OAuth token refresh middleware — pre-AgentMES (buggy template).

This is the file the AgentMES pipeline rewrites during Stage 3 Build
when TKT-001 fires. The version checked in here has the race
condition that causes ``test_oauth_token_refresh`` to flake on ~10%
of CI runs:

- Two concurrent callers of ``get_token()`` for the same session both
  observe an expired token.
- Both call ``_refresh``, both hit the auth server, both write the
  result back via ``_store.put``.
- The second ``put`` clobbers the first, leaving an inconsistent
  token in the cache.

Every Stage 7 Deploy PR commits a fixed copy of this file into its
own ``demo-runs/runs/<run_id>/auth/middleware.py`` so the PR shows a
real code change with a real unified diff. The template itself is
never modified — it's a stable "before" snapshot every run can
branch off.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Token(Protocol):
    refresh_token: str

    def is_expired(self, now: datetime) -> bool: ...


class TokenStore(Protocol):
    async def get(self, session_id: str) -> Token: ...

    async def put(self, session_id: str, token: Token) -> None: ...

    async def refresh(self, session_id: str, refresh_token: str) -> Token: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.utcnow()


class OAuthTokenMiddleware:
    """Manages OAuth token lifecycle for per-session HTTP requests.

    KNOWN BUG: concurrent callers for the same session race inside
    the refresh window. Both see an expired token, both call
    ``_refresh``, and the second ``put`` clobbers the first. The
    flake surfaces in ``test_oauth_token_refresh`` on ~10% of CI runs.
    """

    def __init__(self, token_store: TokenStore, clock: Clock = SystemClock()) -> None:
        self._store = token_store
        self._clock = clock

    async def get_token(self, session_id: str) -> Token:
        token = await self._store.get(session_id)
        if token.is_expired(self._clock.now()):
            token = await self._refresh(session_id, token)
        return token

    async def _refresh(self, session_id: str, stale: Token) -> Token:
        new_token = await self._store.refresh(session_id, stale.refresh_token)
        await self._store.put(session_id, new_token)
        return new_token
