from __future__ import annotations

from typing import Protocol


class ICache(Protocol):
    """A minimal string cache port. The concrete adapter (Valkey) lives in
    infrastructure/cache. Implementations are best-effort: a cache outage degrades to a
    miss, never an error, so the request path never depends on the cache being up."""

    def get(self, key: str) -> str | None:
        ...

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        ...

    def delete(self, key: str) -> None:
        ...
