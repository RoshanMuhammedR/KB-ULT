from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

from src.core.text import sanitize_text_for_storage
from src.domain.entities import AssetStatus, KnowledgeAsset, RawContent
from src.domain.interfaces import IFileStorage

# ATX headings only, levels 1-6 (`#` .. `######`). Setext underlines are rare in
# machine-written Markdown and ambiguous to split on, so a file using them becomes one
# "Introduction" section rather than being split at the wrong boundaries.
# `strip_headers=False` keeps each section's own heading line inside its body, so a cited
# passage reads as a complete section rather than starting mid-sentence. Splitting is
# fence-aware — a `#`-prefixed comment inside a code block is never mistaken for a
# heading, unlike a naive line-by-line regex would.
_HEADER_LEVELS = [("#" * level, f"h{level}") for level in range(1, 7)]

# Text appearing before the first heading still needs a citable locator.
_PREAMBLE_SECTION = "Introduction"

# Used only to find the document's own title (the first real heading, fence-aware) —
# independent of how the splitter above groups sections, since a heading with no content
# of its own before its first child heading gets folded into that child's section.
_HEADING_LINE_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^(```+|~~~+)")


def _first_heading(text: str) -> str | None:
    in_fence = False
    for line in text.splitlines():
        if _FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_LINE_RE.match(line)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return None


class MarkdownSourceHandler:
    """Source handler for uploaded Markdown (implements `ISourceHandler`).

    `acquire` re-reads the uploaded bytes from object storage (the same retry-without-re-upload
    property the PDF handler has), and `parse` splits on ATX headings — via LangChain's
    `MarkdownHeaderTextSplitter` — so each section becomes a citable `Document` with a
    `section` locator.

    This is also the path the app's "paste Markdown" affordance uses — the client builds a
    `.md` File from the textarea and posts it through the ordinary upload endpoint, so
    there is no separate paste API.
    """

    def __init__(self, file_storage: IFileStorage) -> None:
        self.file_storage = file_storage
        self._splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=_HEADER_LEVELS, strip_headers=False
        )

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
        documents = [
            Document(
                page_content=body,
                metadata={"locator": {"type": "section", "value": heading}},
            )
            for heading, body in sections
            if body
        ]
        if not documents:
            raise ValueError("This Markdown file has no readable text in it")

        title = self._title(cleaned, asset.filename)
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
            documents=documents,
            metadata={
                "filename": asset.filename,
                "title": title,
                "source_type": asset.source_type,
                "format": "markdown",
                "content_type": raw.mime or asset.metadata.get("content_type"),
                "headings": len(headings),
                "words": len(cleaned.split()),
            },
        )

    def _split_sections(self, text: str) -> list[tuple[str, str]]:
        """Return `[(heading, body)]` in document order.

        Each split's heading is the deepest header currently active — the last entry in
        its metadata dict, which `MarkdownHeaderTextSplitter` resets whenever a shallower
        heading recurs, so this always matches the most recently seen heading rather than
        going stale on the way back up. Text before the first heading gets "Introduction".
        """
        sections: list[tuple[str, str]] = []
        for document in self._splitter.split_text(text):
            body = document.page_content.strip()
            if not body:
                continue
            heading = list(document.metadata.values())[-1] if document.metadata else _PREAMBLE_SECTION
            sections.append((heading, body))
        return sections

    def _title(self, cleaned_text: str, filename: str) -> str:
        """First real heading anywhere in the document wins; otherwise the filename stem."""
        heading = _first_heading(cleaned_text)
        if heading:
            return sanitize_text_for_storage(heading)
        stem = filename.rsplit(".", 1)[0] if "." in filename else filename
        return sanitize_text_for_storage(stem or filename)
