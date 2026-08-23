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

# Joins a section's ancestor headings into one locator string. ` > ` reads as a path
# to a human and survives being embedded as plain text.
_HEADING_SEPARATOR = " > "

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

    async def acquire(self, asset: KnowledgeAsset) -> RawContent:
        data = await self.file_storage.download(asset.storage_key)
        return RawContent(data=data, mime="text/markdown")

    async def parse(self, asset: KnowledgeAsset, raw: RawContent) -> KnowledgeAsset:
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

        The heading is the full path to the section, not just its own title:
        "Billing > Invoices > Late payment" rather than "Late payment". The splitter
        hands back every currently-active header level in its metadata, and taking only
        the deepest one threw away exactly the context that disambiguates a generic
        heading - half the sections in a real document are called something like
        "Overview" or "Limitations", and on its own that locates nothing.

        The path is what the retrieval layer prefixes to a chunk before embedding, so
        this is the difference between a chunk that reads "Overview" and one that reads
        "Billing > Invoices > Overview". Text before the first heading gets
        "Introduction".
        """
        sections: list[tuple[str, str]] = []
        for document in self._splitter.split_text(text):
            body = document.page_content.strip()
            if not body:
                continue
            # dict order is insertion order, and the splitter inserts shallow-to-deep,
            # so the values already read as a path from the top of the document down.
            trail = [str(value).strip() for value in document.metadata.values() if str(value).strip()]
            heading = _HEADING_SEPARATOR.join(trail) if trail else _PREAMBLE_SECTION
            sections.append((heading, body))
        return sections

    def _title(self, cleaned_text: str, filename: str) -> str:
        """First real heading anywhere in the document wins; otherwise the filename stem."""
        heading = _first_heading(cleaned_text)
        if heading:
            return sanitize_text_for_storage(heading)
        stem = filename.rsplit(".", 1)[0] if "." in filename else filename
        return sanitize_text_for_storage(stem or filename)
