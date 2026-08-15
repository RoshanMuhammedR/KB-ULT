from __future__ import annotations

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

    `parse` runs the PDF loader and emits the source-neutral **segment** structure
    (`metadata["segments"]`, each with a typed `locator`) that the chunker consumes.
    For PDF the locator is the page number; a future YouTube handler would emit a
    timestamp locator with no change to chunking, embedding, or chat.
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

        # Turn the loader's page list into generic segments: {text, locator{type,value}}.
        # `spans` rides alongside — the block rects for this page, which the chunker resolves
        # into highlight regions once it knows where each chunk starts and ends.
        spans_by_page: dict[int, list[dict]] = {}
        for span in parsed.get("spans") or []:
            spans_by_page.setdefault(span["page"], []).append(span)

        segments = []
        text_parts = []
        for page in parsed["pages"]:
            # Clean extracted text before it reaches metadata, chunks, embeddings, or PostgreSQL.
            page_text = sanitize_text_for_storage(page["text"]).strip()
            page_number = page.get("page_number")
            segment: dict = {
                "text": page_text,
                "locator": {"type": "page", "value": page_number},
            }
            page_spans = spans_by_page.get(page_number)
            if page_spans:
                segment["spans"] = page_spans
            segments.append(segment)
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
            metadata={
                "filename": asset.filename,
                "title": title,
                "source_type": asset.source_type,
                "format": "markdown",
                "content_type": raw.mime or asset.metadata.get("content_type"),
                "segments": segments,
                # Page boxes in points, post-rotation — the renderer sizes page images from
                # these, and the viewer sizes its canvas before an image loads.
                "page_boxes": parsed.get("page_boxes") or [],
                "parser": parsed["metadata"],
            },
        )
