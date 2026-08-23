from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class ILLMProvider(Protocol):
    """Chat completion, sync-shaped and streaming.

    `stream` is on the port deliberately: the SSE path depends on it, and leaving it off
    meant the interface described less than the system actually required.
    """

    async def generate(self, messages: list[dict[str, str]]) -> str:
        ...

    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Yield the answer in pieces as the model produces them.

        Not `async def`: an async *generator* function returns its iterator directly, so
        callers write `async for piece in provider.stream(...)` with no extra await.
        """
        ...
