from __future__ import annotations

from typing import Any

from src.core.text import sanitize_text_for_storage

# PDF-generating tools commonly leave one of these as the literal metadata title when the
# author never set a real one - trusting them verbatim produces a display name that's worse
# than just falling back to the filename (the caller's fallback for a None title).
_PLACEHOLDER_TITLES = {"anonymous", "untitled", "untitled document", "no title", "document", "new document"}


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
            geometry = self._extract_geometry(document)
        finally:
            document.close()

        return {
            "markdown": markdown,
            "pages": pages,
            # Per-page text blocks with normalized rects, and the page boxes themselves.
            # Consumed by the chunker to turn a chunk's character span into highlight
            # rectangles, and by the renderer to size page images.
            "spans": geometry["spans"],
            "page_boxes": geometry["page_boxes"],
            "title": title,
            "metadata": {
                "status": "success",
                "errors": 0,
                "page_count": page_count,
            },
        }

    def _extract_geometry(self, document: Any) -> dict[str, Any]:
        """Per-block text + rects, normalized to fractions of the page box.

        PyMuPDF hands out block rectangles for free during text extraction; the markdown path
        discards them. Capturing them here is what lets a citation highlight the actual lines
        it came from instead of colouring a whole page.

        Rects are `[x0, y0, x1, y1]` as fractions of `page.rect`, origin top-left. Fractions
        rather than points so the client can multiply by whatever pixel size the image was
        rendered at — resolution independence falls out for free. `page.rect` already accounts
        for `page.rotation`, so rotation is baked in here and the client never does that math.
        """
        spans: list[dict[str, Any]] = []
        page_boxes: list[dict[str, Any]] = []

        for page_index, page in enumerate(document, start=1):
            rect = page.rect
            width = float(rect.width) or 1.0
            height = float(rect.height) or 1.0
            page_boxes.append({"n": page_index, "w": round(width, 2), "h": round(height, 2)})

            try:
                blocks = page.get_text("blocks")
            except Exception:  # noqa: BLE001 - geometry is an enhancement, never fail parsing
                continue

            for block in blocks:
                # (x0, y0, x1, y1, text, block_no, block_type); type 1 is an image block.
                if len(block) < 7 or block[6] != 0:
                    continue
                text = sanitize_text_for_storage(str(block[4] or "")).strip()
                if not text:
                    continue
                spans.append(
                    {
                        "page": page_index,
                        "text": text,
                        "rect": [
                            round(max(0.0, min(1.0, float(block[0]) / width)), 5),
                            round(max(0.0, min(1.0, float(block[1]) / height)), 5),
                            round(max(0.0, min(1.0, float(block[2]) / width)), 5),
                            round(max(0.0, min(1.0, float(block[3]) / height)), 5),
                        ],
                    }
                )

        return {"spans": spans, "page_boxes": page_boxes}

    def _extract_pages(self, page_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Number by position in the FULL chunk list, then drop the empty pages - never the
        # other way around. pymupdf4llm appends one dict per page in page order, empty pages
        # included, so `enumerate` over the unfiltered list is the true 1-indexed page number.
        # Filtering first and numbering the survivors would make every page after a blank or
        # image-only one cite a number lower than its real page, silently.
        #
        # Position is preferred over the chunk's own metadata["page"] only because it needs no
        # trust in an undocumented convention; the two agree (that field is `pno + 1`).
        pages = []
        for page_number, chunk in enumerate(page_chunks, start=1):
            text = sanitize_text_for_storage(chunk.get("text", "")).strip()
            if text:
                pages.append({"page_number": page_number, "text": text})
        return pages

    def _extract_title(self, document: Any, filename: str) -> str | None:
        title = (document.metadata or {}).get("title")
        if not title:
            return None
        cleaned = sanitize_text_for_storage(str(title)).strip()
        normalized = cleaned.strip("()[] ").lower()
        if not cleaned or normalized in _PLACEHOLDER_TITLES:
            return None
        return cleaned
