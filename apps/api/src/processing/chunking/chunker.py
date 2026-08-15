from __future__ import annotations

from src.domain.entities import Chunk, KnowledgeAsset
from src.infrastructure.langchain_adapters.text_splitter import RecursiveSplitterAdapter


class RecursiveKnowledgeAssetChunker:
    def __init__(self, splitter: RecursiveSplitterAdapter) -> None:
        self.splitter = splitter

    def chunk(self, asset: KnowledgeAsset) -> list[Chunk]:
        # Handlers normalize every source into `segments` (text + a typed locator), so
        # chunking is source-agnostic: it never knows or cares whether a locator is a
        # page number or a timestamp.
        segments = asset.metadata.get("segments", [])
        split_chunks = self.splitter.split_segments(segments)
        chunks: list[Chunk] = []
        for index, split in enumerate(split_chunks):
            chunks.append(
                Chunk(
                    knowledge_asset_id=asset.id,
                    chunk_index=index,
                    text=split["text"],
                    metadata={
                        "filename": asset.filename,
                        "title": asset.title,
                        "locator": split.get("locator"),
                        "source_type": asset.source_type,
                        "knowledge_base_id": str(asset.knowledge_base_id),
                        "knowledge_asset_id": str(asset.id),
                        "chunk_index": index,
                    },
                )
            )
        return chunks
