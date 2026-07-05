from __future__ import annotations

from src.domain.entities import Chunk, KnowledgeAsset
from src.infrastructure.langchain_adapters.text_splitter import RecursiveSplitterAdapter


class RecursiveKnowledgeAssetChunker:
    def __init__(self, splitter: RecursiveSplitterAdapter) -> None:
        self.splitter = splitter

    def chunk(self, asset: KnowledgeAsset) -> list[Chunk]:
        pages = asset.metadata.get("pages", [])
        split_chunks = self.splitter.split_pages(pages)
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
                        "page_number": split.get("page_number"),
                        "source_type": asset.source_type,
                        "knowledge_base_id": str(asset.knowledge_base_id),
                        "knowledge_asset_id": str(asset.id),
                        "chunk_index": index,
                    },
                )
            )
        return chunks
