from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from src.domain.entities import KnowledgeAsset

if TYPE_CHECKING:
    from src.ingestion.sources.file_source import FileSource


class IParser(Protocol):
    def parse(self, source: FileSource) -> KnowledgeAsset:
        """Normalize a raw source into a KnowledgeAsset."""
