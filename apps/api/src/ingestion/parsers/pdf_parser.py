from __future__ import annotations

from src.core.text import sanitize_text_for_storage
from src.domain.entities import AssetStatus, KnowledgeAsset
from src.infrastructure.document_parsing import DoclingPDFAdapter
from src.ingestion.sources.file_source import FileSource


class PDFParser:
    def __init__(self, loader: DoclingPDFAdapter) -> None:
        self.loader = loader

    def parse(self, source: FileSource) -> KnowledgeAsset:
        parsed = self.loader.load(source.file_data, source.filename)
        pages = parsed["pages"]
        normalized_pages = []
        text_parts = []
        for page in pages:
            page_number = page.get("page_number")
            # Clean extracted text before it reaches asset metadata, chunks, embeddings, or PostgreSQL.
            page_text = sanitize_text_for_storage(page["text"]).strip()
            normalized_pages.append({"page_number": page_number, "text": page_text})
            text_parts.append(page_text)

        title = sanitize_text_for_storage(parsed.get("title") or source.filename)
        markdown = sanitize_text_for_storage(parsed["markdown"]).strip()

        return KnowledgeAsset(
            id=source.asset_id,
            knowledge_base_id=source.knowledge_base_id,
            lineage_id=source.lineage_id,
            version=source.version,
            filename=source.filename,
            title=title,
            source_type="pdf",
            storage_key=source.storage_key,
            status=AssetStatus.EXTRACTING,
            text_content=markdown or "\n\n".join(text_parts),
            metadata={
                "filename": source.filename,
                "title": title,
                "source_type": "pdf",
                "format": "markdown",
                "content_type": source.content_type,
                "pages": normalized_pages,
                "docling": parsed["metadata"],
            },
        )
