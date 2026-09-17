"""Token blocklist.

Revoked token IDs are stored with a TTL matching the token's own expiry, so the
blocklist never grows without bound. Redis is used when REDIS_URL is configured;
otherwise an in-process dict keeps single-instance deployments and the test
suite working without extra infrastructure.
"""

import contextlib
import time

from src.config import settings

_REVOKED_PREFIX = "revoked:"


class InMemoryBlocklist:
    """Process-local fallback. Not shared between workers - dev/test only."""

    def __init__(self) -> None:
        self._entries: dict[str, float] = {}

    def _purge(self) -> None:
        now = time.monotonic()
        for key, expires_at in list(self._entries.items()):
            if expires_at <= now:
                del self._entries[key]

    async def set(self, key: str, value: str, ex: int) -> None:
        self._purge()
        self._entries[key] = time.monotonic() + max(ex, 0)

    async def get(self, key: str) -> str | None:
        self._purge()
        return "1" if key in self._entries else None

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self._entries.clear()


def _build_client():
    if settings.uses_redis:
        import redis.asyncio as redis

        return redis.from_url(settings.REDIS_URL, decode_responses=True)
    return InMemoryBlocklist()


redis_client = _build_client()


async def revoke_token(jti: str, expires_in: int) -> None:
    # A token that already expired needs no entry; Redis rejects ex <= 0 anyway.
    if expires_in <= 0:
        return
    await redis_client.set(f"{_REVOKED_PREFIX}{jti}", "1", ex=expires_in)


async def is_token_revoked(jti: str) -> bool:
    return await redis_client.get(f"{_REVOKED_PREFIX}{jti}") is not None


async def blocklist_healthy() -> bool:
    try:
        await redis_client.ping()
        return True
    except Exception:
        return False


async def close_blocklist() -> None:
    with contextlib.suppress(Exception):
        await redis_client.aclose()
