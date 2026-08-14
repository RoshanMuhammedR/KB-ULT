from __future__ import annotations

import re

from src.core.text import sanitize_text_for_storage
from src.domain.entities import AssetStatus, KnowledgeAsset, RawContent
from src.domain.interfaces import IFileStorage

# ATX headings only (`# Heading`). Setext underlines are rare in machine-written Markdown
# and ambiguous to split on, so a file using them becomes one "Introduction" section
# rather than being mis-segmented.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

# Text appearing before the first heading still needs a citable locator.
_PREAMBLE_SECTION = "Introduction"


class MarkdownSourceHandler:
    """Source handler for uploaded Markdown (implements `ISourceHandler`).

    The simplest possible handler: no parsing dependency at all. `acquire` re-reads the
    uploaded bytes from object storage (the same retry-without-re-upload property the PDF
    handler has), and `parse` splits on ATX headings so each section becomes a citable
    segment with a `section` locator.

    This is also the path the app's "paste Markdown" affordance uses — the client builds a
    `.md` File from the textarea and posts it through the ordinary upload endpoint, so
    there is no separate paste API.
    """

    def __init__(self, file_storage: IFileStorage) -> None:
        self.file_storage = file_storage

    def acquire(self, asset: KnowledgeAsset) -> RawContent:
        data = self.file_storage.download(asset.storage_key)
        return RawContent(data=data, mime="text/markdown")

    def parse(self, asset: KnowledgeAsset, raw: RawContent) -> KnowledgeAsset:
        text = raw.data.decode("utf-8", errors="replace") if isinstance(raw.data, bytes) else raw.data
        cleaned = sanitize_text_for_storage(text)
        if not cleaned.strip():
            # Lands in the existing failed + retry path with a message the user can act on.
            raise ValueError("This Markdown file has no readable text in it")

        sections = self._split_sections(cleaned)
        segments = [
            {"text": body, "locator": {"type": "section", "value": heading}}
            for heading, body in sections
            if body
        ]
        if not segments:
            raise ValueError("This Markdown file has no readable text in it")

        title = self._title(sections, asset.filename)
        headings = [heading for heading, _ in sections]

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
            text_content=cleaned.strip(),
            metadata={
                "filename": asset.filename,
                "title": title,
                "source_type": asset.source_type,
                "format": "markdown",
                "content_type": raw.mime or asset.metadata.get("content_type"),
                "headings": len(headings),
                "words": len(cleaned.split()),
                "segments": segments,
            },
        )

    def _split_sections(self, text: str) -> list[tuple[str, str]]:
        """Return `[(heading, body)]` in document order.

        The heading line itself is kept inside the body so a cited passage reads as a
        complete section rather than starting mid-sentence.
        """
        sections: list[tuple[str, list[str]]] = []
        current_heading = _PREAMBLE_SECTION
        current_lines: list[str] = []

        for line in text.splitlines():
            match = _HEADING_RE.match(line)
            if match:
                if current_lines:
                    sections.append((current_heading, current_lines))
                current_heading = match.group(2).strip() or _PREAMBLE_SECTION
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            sections.append((current_heading, current_lines))

        return [(heading, "\n".join(lines).strip()) for heading, lines in sections]

    def _title(self, sections: list[tuple[str, str]], filename: str) -> str:
        """First real heading wins; otherwise the filename, minus its extension."""
        for heading, _ in sections:
            if heading != _PREAMBLE_SECTION:
                return sanitize_text_for_storage(heading)
        stem = filename.rsplit(".", 1)[0] if "." in filename else filename
        return sanitize_text_for_storage(stem or filename)
