from __future__ import annotations

import re

import structlog
from langchain_core.documents import Document

from src.domain.entities import Chunk, ChunkModality, KnowledgeAsset, SourceType
from src.domain.interfaces.llm import ILLMProvider
from src.infrastructure.langchain_adapters.text_splitter import RecursiveSplitterAdapter

logger = structlog.get_logger(__name__)

# Which chunks were produced by a machine reading something, rather than by a person typing
# it. ASR and OCR text is noisier at identical relevance, so retrieval holds it to a higher
# score before citing it.
_MODALITY_BY_SOURCE = {
    SourceType.PDF: ChunkModality.PDF,
    SourceType.MARKDOWN: ChunkModality.TEXT,
    SourceType.PPTX: ChunkModality.TEXT,
    SourceType.AUDIO: ChunkModality.ASR,
    SourceType.YOUTUBE: ChunkModality.ASR,
}

# An ATX markdown heading at the start of a line: `## Termination`. PyMuPDF4LLM emits these
# for PDF headings, python-pptx gives us slide titles, and markdown sources have them
# natively — so one pattern recovers document structure across every source type we ingest.
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

# A section longer than this is split into several parents. Without a ceiling, a document
# with no headings would produce one parent holding the entire text, and "expand to the
# parent" would then mean "send the whole document".
_MAX_PARENT_CHARS = 6000

# Enrichment is skipped for sections this short: there is nothing to summarise, and the
# blurb would cost a model call to restate the text it precedes.
_MIN_CHARS_TO_ENRICH = 200

_CONTEXT_PROMPT = (
    "Here is a section of the document '{title}':\n\n"
    "<section>\n{section}\n</section>\n\n"
    "Write ONE short sentence (max 25 words) that situates this section within the document, "
    "so a reader who sees only an excerpt of it knows what it is about. State the subject "
    "plainly. Do not add preamble, quotes, or explanation."
)


class StructureAwareChunker:
    """Splits a source into parent sections and the child chunks that are actually searched.

    Three things happen here, and all three exist because retrieval quality is decided at
    ingestion time — no amount of clever querying recovers from chunks that were cut in the
    wrong place or that read as fragments.

    **Structure first.** Handlers hand us one `Document` per page, slide, or timestamp
    window, and those documents carry markdown headings in their text. Splitting on those
    headings before splitting on size means a chunk boundary lands between two ideas rather
    than in the middle of one.

    **Small-to-big.** Each section becomes a *parent*; the parent is then split into
    *children* of a few hundred tokens. Children are what get embedded and matched, because
    a small chunk matches precisely. The parent is what reaches the model, because a section
    is what actually contains the answer. Fixed-size windows have to choose one or the
    other; this does not.

    **Contextual enrichment.** A child that reads "It expires after 30 days." is unfindable
    on its own. Prefixing a one-line description of its section before embedding makes it
    retrievable, while `text` stays exactly what gets displayed and cited.

    The blurb is generated once per *section*, not per chunk. Per chunk is what the
    literature describes, but a 200-page PDF is ~600 chunks and therefore ~600 model calls
    per document on a paid gateway; per section it is nearer 60, and every child of a
    section shares its context anyway.
    """

    def __init__(
        self,
        splitter: RecursiveSplitterAdapter,
        llm_provider: ILLMProvider | None = None,
        *,
        enrich: bool = True,
    ) -> None:
        self.splitter = splitter
        self.llm_provider = llm_provider
        # Enrichment is optional so ingestion still works with no gateway configured, and so
        # a caller can turn off the cost without changing the object graph.
        self.enrich = enrich and llm_provider is not None

    async def chunk(self, asset: KnowledgeAsset) -> list[Chunk]:
        modality = self._modality(asset)
        sections = self._sections(asset.documents)
        if not sections:
            return []

        chunks: list[Chunk] = []
        index = 0

        for section in sections:
            children = self.splitter.split([section])
            if not children:
                continue

            heading = section.metadata.get("heading")
            context = await self._describe(asset, section)

            parent = Chunk(
                knowledge_asset_id=asset.id,
                chunk_index=index,
                text=section.page_content,
                parent_id=None,
                modality=modality,
                metadata=self._metadata(asset, section, index, heading=heading, is_parent=True),
            )
            index += 1

            child_chunks = []
            for child in children:
                child_chunks.append(
                    Chunk(
                        knowledge_asset_id=asset.id,
                        chunk_index=index,
                        text=child.page_content,
                        parent_id=parent.id,
                        modality=modality,
                        embed_text=self._embed_text(child.page_content, context, heading),
                        metadata=self._metadata(asset, child, index, heading=heading),
                    )
                )
                index += 1

            chunks.append(parent)
            chunks.extend(child_chunks)

        logger.info(
            "asset_chunked",
            knowledge_asset_id=str(asset.id),
            sections=sum(1 for c in chunks if c.is_parent),
            children=sum(1 for c in chunks if not c.is_parent),
            enriched=self.enrich,
            modality=modality,
        )
        return chunks

    # --- structure -----------------------------------------------------------------

    def _sections(self, documents: list[Document]) -> list[Document]:
        """Turn per-page documents into per-section documents, preserving locators.

        A section never spans two source documents: a page break is also a locator change,
        and a chunk that straddled one could not be cited to a single place.
        """
        sections: list[Document] = []
        for document in documents:
            for piece in self._split_by_heading(document):
                sections.extend(self._cap_length(piece))
        return sections

    def _split_by_heading(self, document: Document) -> list[Document]:
        text = document.page_content
        matches = list(_HEADING.finditer(text))
        if not matches:
            return [document]

        pieces: list[Document] = []

        # Text before the first heading is its own section — a page that continues a
        # section started on the previous page still has content worth keeping.
        preamble = text[: matches[0].start()].strip()
        if preamble:
            pieces.append(self._derive(document, preamble, heading=document.metadata.get("heading")))

        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[match.start() : end].strip()
            if body:
                pieces.append(self._derive(document, body, heading=match.group(2).strip()))
        return pieces

    def _cap_length(self, document: Document) -> list[Document]:
        """Bound a section so "expand to the parent" can never mean "send the document"."""
        text = document.page_content
        if len(text) <= _MAX_PARENT_CHARS:
            return [document]
        return [
            self._derive(document, text[start : start + _MAX_PARENT_CHARS], heading=document.metadata.get("heading"))
            for start in range(0, len(text), _MAX_PARENT_CHARS)
        ]

    @staticmethod
    def _derive(source: Document, text: str, *, heading: str | None) -> Document:
        metadata = dict(source.metadata)
        if heading:
            metadata["heading"] = heading
        return Document(page_content=text, metadata=metadata)

    # --- enrichment ----------------------------------------------------------------

    async def _describe(self, asset: KnowledgeAsset, section: Document) -> str:
        if not self.enrich or len(section.page_content) < _MIN_CHARS_TO_ENRICH:
            return ""
        prompt = _CONTEXT_PROMPT.format(
            title=asset.title or asset.filename,
            # Only the head of the section: the model needs to recognise the subject, not
            # read the whole thing, and the prompt is billed either way.
            section=section.page_content[:1500],
        )
        try:
            described = await self.llm_provider.generate([{"role": "user", "content": prompt}])
        except Exception:  # noqa: BLE001 - enrichment is an optimisation, never a blocker
            # Ingestion must not fail because the describing model was unavailable. The
            # chunk simply embeds as itself, which is what it did before this existed.
            logger.warning("chunk_context_unavailable", knowledge_asset_id=str(asset.id))
            return ""
        return " ".join(described.split())[:300]

    @staticmethod
    def _embed_text(text: str, context: str, heading: str | None) -> str:
        """Assemble what actually gets vectorised. Empty means "embed `text` as-is".

        The heading is prepended only when the chunk does not already open with it. A
        section keeps its own heading line in its body, so the first child of every
        section would otherwise carry the heading twice - which dilutes the embedding
        with a repeated token rather than adding anything.
        """
        parts = []
        if context:
            parts.append(context)
        opening = text[: len(heading) + 8].lower() if heading else ""
        if heading and heading.lower() not in opening:
            parts.append(heading)
        prefix = " ".join(parts)
        return f"{prefix}\n\n{text}" if prefix else ""


    # --- misc ----------------------------------------------------------------------

    @staticmethod
    def _modality(asset: KnowledgeAsset) -> str:
        try:
            source = SourceType(asset.source_type)
        except ValueError:
            return ChunkModality.TEXT.value
        return _MODALITY_BY_SOURCE.get(source, ChunkModality.TEXT).value

    @staticmethod
    def _metadata(
        asset: KnowledgeAsset,
        document: Document,
        index: int,
        *,
        heading: str | None = None,
        is_parent: bool = False,
    ) -> dict:
        return {
            "filename": asset.filename,
            "title": asset.title,
            "locator": document.metadata.get("locator"),
            "heading": heading,
            "source_type": asset.source_type,
            "knowledge_base_id": str(asset.knowledge_base_id),
            "knowledge_asset_id": str(asset.id),
            "chunk_index": index,
            "is_parent": is_parent,
        }


# The previous name, kept so the composition root and any pickled references keep resolving.
RecursiveKnowledgeAssetChunker = StructureAwareChunker
