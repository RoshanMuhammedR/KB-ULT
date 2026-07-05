from __future__ import annotations

from typing import Protocol

from src.domain.entities import Embedding


class IEmbedder(Protocol):
    def embed_texts(self, texts: list[str]) -> list[Embedding]:
        """Return one embedding for each input text."""
