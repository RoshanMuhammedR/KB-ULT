from __future__ import annotations

from src.domain.entities import Chunk, KnowledgeAsset
from src.infrastructure.langchain_adapters.text_splitter import RecursiveSplitterAdapter


class RecursiveKnowledgeAssetChunker:
    def __init__(self, splitter: RecursiveSplitterAdapter) -> None:
        self.splitter = splitter

    def chunk(self, asset: KnowledgeAsset) -> list[Chunk]:
        # Handlers normalize every source into `Document`s (text + a typed locator in
        # metadata), so chunking is source-agnostic: it never knows or cares whether a
        # locator is a page number or a timestamp. The splitter carries each document's
        # metadata onto every piece it produces, which is what keeps a chunk citable.
        split_documents = self.splitter.split(asset.documents)
        chunks: list[Chunk] = []
        for index, document in enumerate(split_documents):
            chunks.append(
                Chunk(
                    knowledge_asset_id=asset.id,
                    chunk_index=index,
                    text=document.page_content,
                    metadata={
                        "filename": asset.filename,
                        "title": asset.title,
                        "locator": document.metadata.get("locator"),
                        "source_type": asset.source_type,
                        "knowledge_base_id": str(asset.knowledge_base_id),
                        "knowledge_asset_id": str(asset.id),
                        "chunk_index": index,
                    },
                )
            )
        return chunks
