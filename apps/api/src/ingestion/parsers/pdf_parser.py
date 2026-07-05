from __future__ import annotations

from src.core.text import sanitize_text_for_storage
from src.domain.entities import AssetStatus, KnowledgeAsset
from src.infrastructure.langchain_adapters.pdf_loader import PdfLoaderAdapter
from src.ingestion.sources.file_source import FileSource


class PDFParser:
    def __init__(self, loader: PdfLoaderAdapter) -> None:
        self.loader = loader

    def parse(self, source: FileSource) -> KnowledgeAsset:
        pages = self.loader.load_pages(source.file_data)
        normalized_pages = []
        text_parts = []
        for index, page in enumerate(pages, start=1):
            metadata = page.get("metadata", {})
            page_number = int(metadata.get("page", index - 1)) + 1
            page_text = sanitize_text_for_storage(page["text"]).strip()
            normalized_pages.append({"page_number": page_number, "text": page_text})
            text_parts.append(page_text)

        title = source.filename
        if pages and pages[0].get("metadata", {}).get("title"):
            title = sanitize_text_for_storage(str(pages[0]["metadata"]["title"]))

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
            text_content="\n\n".join(text_parts),
            metadata={
                "filename": source.filename,
                "title": title,
                "source_type": "pdf",
                "content_type": source.content_type,
                "pages": normalized_pages,
            },
        )
