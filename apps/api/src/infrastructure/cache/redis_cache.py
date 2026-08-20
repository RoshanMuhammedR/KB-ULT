from __future__ import annotations

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

# A cache round-trip that takes longer than this is worse than no cache at all: every
# millisecond spent waiting on Redis is a millisecond stolen from the retrieval budget it
# exists to protect. Fail fast and treat it as a miss.
_SOCKET_TIMEOUT_SECONDS = 1.0


class RedisCache:
    """`ICache` backed by Redis (or Valkey — same protocol, same client).

    Best-effort by construction: any connection or timeout error degrades to a miss or a
    no-op and is logged, so a cache outage can never break a request. That property is the
    reason callers never need to handle cache errors themselves.

    The client is created lazily and reused, since it owns a connection pool that should
    outlive any single request.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Redis | None = None

    @property
    def client(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(
                self._url,
                socket_timeout=_SOCKET_TIMEOUT_SECONDS,
                socket_connect_timeout=_SOCKET_TIMEOUT_SECONDS,
            )
        return self._client

    async def get(self, key: str) -> str | None:
        try:
            value = await self.client.get(key)
        except Exception:  # noqa: BLE001 - cache is best-effort; a miss is safe
            logger.warning("cache_get_failed", key=key)
            return None
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else value

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        try:
            await self.client.set(key, value, ex=ttl_seconds)
        except Exception:  # noqa: BLE001 - failing to cache must not fail the request
            logger.warning("cache_set_failed", key=key)

    async def delete(self, key: str) -> None:
        try:
            await self.client.delete(key)
        except Exception:  # noqa: BLE001
            logger.warning("cache_delete_failed", key=key)

    async def close(self) -> None:
        """Release the connection pool. Called from the FastAPI lifespan on shutdown."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
