from __future__ import annotations

from typing import Any

from src.core.text import sanitize_text_for_storage


class PyMuPDF4LLMAdapter:
    """PDF -> markdown extraction via PyMuPDF4LLM (pure Python, no local ML models).

    Replaces the earlier Docling-based adapter: this app's ingestion never enabled
    Docling's OCR or ML table-structure detection by default, so the only thing that
    torch dependency bought was layout-aware markdown extraction we could already get
    from PyMuPDF directly - at a fraction of the image size and with no model weights
    to load. If OCR or ML-driven table structure is ever genuinely needed, reintroduce
    a Docling (or similar) adapter behind this same `.load()` interface rather than
    growing this one.
    """

    def load(self, file_data: bytes, filename: str) -> dict[str, Any]:
        import pymupdf
        import pymupdf4llm

        document = pymupdf.open(stream=file_data, filetype="pdf")
        try:
            # page_chunks=True gives one dict per page instead of one flat string, which is
            # what the rest of the ingestion pipeline (segments -> chunks -> embeddings) wants.
            page_chunks = pymupdf4llm.to_markdown(document, page_chunks=True)
            pages = self._extract_pages(page_chunks)
            markdown = "\n\n".join(page["text"] for page in pages)
            title = self._extract_title(document, filename)
            page_count = document.page_count
        finally:
            document.close()

        return {
            "markdown": markdown,
            "pages": pages,
            "title": title,
            "metadata": {
                "status": "success",
                "errors": 0,
                "page_count": page_count,
            },
        }

    def _extract_pages(self, page_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Number pages by list position (1-indexed) rather than trusting the chunk's own
        # metadata["page"] field - PyMuPDF4LLM's indexing convention there isn't documented
        # clearly enough to rely on, and the chunks are already returned in page order.
        pages = []
        for page_number, chunk in enumerate(page_chunks, start=1):
            text = sanitize_text_for_storage(chunk.get("text", "")).strip()
            if text:
                pages.append({"page_number": page_number, "text": text})
        return pages

    def _extract_title(self, document: Any, filename: str) -> str | None:
        title = (document.metadata or {}).get("title")
        if title:
            return sanitize_text_for_storage(str(title))
        return None
