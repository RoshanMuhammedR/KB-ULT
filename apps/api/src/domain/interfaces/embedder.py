from __future__ import annotations

from typing import Protocol

from src.domain.entities import Embedding


class IEmbedder(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[Embedding]:
        """Return one embedding for each input text."""

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single search query. The only embedding call on the read path."""
        ...
