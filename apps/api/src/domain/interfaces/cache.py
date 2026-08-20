from __future__ import annotations

from typing import Protocol


class ICache(Protocol):
    """A minimal string cache port. The concrete adapter (Redis) lives in
    infrastructure/cache.

    Async because every caller is: the query path that caches embeddings, rerank results
    and answers runs on the event loop, and a synchronous round-trip there would block it.

    Implementations are best-effort: a cache outage degrades to a miss, never an error, so
    the request path never depends on the cache being up.
    """

    async def get(self, key: str) -> str | None:
        ...

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        ...

    async def delete(self, key: str) -> None:
        ...
