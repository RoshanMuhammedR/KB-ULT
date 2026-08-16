from __future__ import annotations

from langchain_core.documents import Document

from src.core.text import sanitize_text_for_storage
from src.domain.entities import AssetStatus, KnowledgeAsset, RawContent
from src.domain.interfaces import IFileStorage
from src.infrastructure.document_parsing import PyMuPDF4LLMAdapter


class PdfSourceHandler:
    """Source handler for uploaded PDFs (implements `ISourceHandler`).

    `acquire` re-reads the uploaded bytes from object storage — the worker never
    receives file bytes through the queue payload, only the asset id, so the source
    is fetched here at process time (this is also what makes a failed extraction
    retryable without a re-upload).

    `parse` runs the PDF loader and emits one `Document` per page, each carrying a typed
    `metadata["locator"]` that the chunker copies onto every chunk it produces. For PDF
    the locator is the page number; the YouTube and audio handlers emit timestamp
    locators from the same field, so chunking, embedding, and chat never special-case a
    source.
    """

    def __init__(self, loader: PyMuPDF4LLMAdapter, file_storage: IFileStorage) -> None:
        self.loader = loader
        self.file_storage = file_storage

    def acquire(self, asset: KnowledgeAsset) -> RawContent:
        data = self.file_storage.download(asset.storage_key)
        return RawContent(data=data, mime="application/pdf")

    def parse(self, asset: KnowledgeAsset, raw: RawContent) -> KnowledgeAsset:
        # The loader wants bytes; acquire always hands us bytes for PDF.
        file_data = raw.data if isinstance(raw.data, bytes) else raw.data.encode("utf-8")
        parsed = self.loader.load(file_data, asset.filename)

        # Turn the loader's page list into one Document per page, each located by page number.
        documents = []
        text_parts = []
        for page in parsed["pages"]:
            # Clean extracted text before it reaches chunks, embeddings, or PostgreSQL.
            page_text = sanitize_text_for_storage(page["text"]).strip()
            documents.append(
                Document(
                    page_content=page_text,
                    metadata={"locator": {"type": "page", "value": page.get("page_number")}},
                )
            )
            text_parts.append(page_text)

        title = sanitize_text_for_storage(parsed.get("title") or asset.filename)
        markdown = sanitize_text_for_storage(parsed["markdown"]).strip()

        return KnowledgeAsset(
            id=asset.id,
            knowledge_base_id=asset.knowledge_base_id,
            lineage_id=asset.lineage_id,
            version=asset.version,
            filename=asset.filename,
            title=title,
            source_type=asset.source_type,
            storage_key=asset.storage_key,
            status=AssetStatus.EXTRACTING,
            text_content=markdown or "\n\n".join(text_parts),
            documents=documents,
            metadata={
                "filename": asset.filename,
                "title": title,
                "source_type": asset.source_type,
                "format": "markdown",
                "content_type": raw.mime or asset.metadata.get("content_type"),
                "parser": parsed["metadata"],
            },
        )
