from __future__ import annotations

from src.domain.entities import KnowledgeAsset
from src.ingestion.registry import ParserRegistry
from src.ingestion.sources.file_source import FileSource


class IngestionPipeline:
    def __init__(self, parser_registry: ParserRegistry) -> None:
        self.parser_registry = parser_registry

    def parse(self, source: FileSource) -> KnowledgeAsset:
        return self.parser_registry.get(source.filename).parse(source)
