"""String constants of the fixed source files AgentMES commits at Deploy.

At Stage 7, ``DeployStage._open_real_pr`` reads the buggy template at
``demo-runs/code-template/auth/middleware.py``, writes the fixed
version below into a per-run subdirectory under ``demo-runs/runs/``,
computes the unified diff, and commits all three files (fixed code,
diff, receipt log). The PR shows a real code change reviewers could
actually merge — not just a markdown log.

Keep FIXED_OAUTH_MIDDLEWARE in lockstep with the template; the diff
computed at commit time is the literal difference between the two.
"""

from __future__ import annotations

# Path relative to the repo root where the buggy template lives.
TEMPLATE_MIDDLEWARE_PATH = "demo-runs/code-template/auth/middleware.py"


FIXED_OAUTH_MIDDLEWARE = '''"""OAuth token refresh middleware — single-flight refresh lock fix.

Fix authored by AgentMES Stage 3 Build against the race documented
in ``demo-runs/code-template/auth/middleware.py``.

Approach: coalesce concurrent refresh futures on a per-session
``asyncio.Lock`` + in-flight future dict. The second caller for a
given ``session_id`` awaits the first caller's future instead of
racing. Only one HTTP call hits the auth server per refresh window,
and only one ``put`` lands in the token cache — the race that caused
``test_oauth_token_refresh`` to flake on ~10% of CI runs is gone.

No test mocks were touched. The fix lives in production code, as the
TKT-001 ticket required.
"""

from __future__ import annotations

import asyncio
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

    Single-flight refresh: concurrent callers for the same session
    share one HTTP call to the auth server. The refresh lock and
    inflight future dict together eliminate the race that caused
    ``test_oauth_token_refresh`` to flake on ~10% of CI runs.
    """

    def __init__(self, token_store: TokenStore, clock: Clock = SystemClock()) -> None:
        self._store = token_store
        self._clock = clock
        self._refresh_lock = asyncio.Lock()
        self._inflight: dict[str, asyncio.Future[Token]] = {}

    async def get_token(self, session_id: str) -> Token:
        token = await self._store.get(session_id)
        if not token.is_expired(self._clock.now()):
            return token
        return await self._coalesced_refresh(session_id, token)

    async def _coalesced_refresh(self, session_id: str, stale: Token) -> Token:
        # Single-flight — if another caller is already refreshing this
        # session, await their future instead of racing a duplicate.
        async with self._refresh_lock:
            existing = self._inflight.get(session_id)
            if existing is not None:
                return await existing
            fut: asyncio.Future[Token] = asyncio.get_event_loop().create_future()
            self._inflight[session_id] = fut
        try:
            refreshed = await self._refresh(session_id, stale)
            fut.set_result(refreshed)
            return refreshed
        except Exception as exc:
            fut.set_exception(exc)
            raise
        finally:
            async with self._refresh_lock:
                self._inflight.pop(session_id, None)

    async def _refresh(self, session_id: str, stale: Token) -> Token:
        refreshed = await self._store.refresh(session_id, stale.refresh_token)
        await self._store.put(session_id, refreshed)
        return refreshed
'''
