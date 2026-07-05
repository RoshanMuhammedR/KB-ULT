from __future__ import annotations

from typing import Protocol

from src.domain.entities import Chunk, KnowledgeAsset


class IChunker(Protocol):
    def chunk(self, asset: KnowledgeAsset) -> list[Chunk]:
        """Split a parsed KnowledgeAsset into chunks."""
