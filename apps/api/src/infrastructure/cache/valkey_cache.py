from __future__ import annotations

import structlog
from valkey import Valkey

logger = structlog.get_logger(__name__)


class ValkeyCache:
    """`ICache` backed by Valkey (Redis-protocol). Best-effort: any connection/timeout
    error degrades to a cache miss / no-op and is logged, so a cache outage never breaks
    a request. The client is created lazily and reused (its own connection pool)."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Valkey | None = None

    @property
    def client(self) -> Valkey:
        if self._client is None:
            self._client = Valkey.from_url(
                self._url, socket_timeout=1.0, socket_connect_timeout=1.0
            )
        return self._client

    def get(self, key: str) -> str | None:
        try:
            value = self.client.get(key)
        except Exception:  # noqa: BLE001 - cache is best-effort; a miss is safe
            logger.warning("cache_get_failed", key=key)
            return None
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else value

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        try:
            self.client.set(key, value, ex=ttl_seconds)
        except Exception:  # noqa: BLE001 - failing to cache must not fail the request
            logger.warning("cache_set_failed", key=key)

    def delete(self, key: str) -> None:
        try:
            self.client.delete(key)
        except Exception:  # noqa: BLE001
            logger.warning("cache_delete_failed", key=key)
