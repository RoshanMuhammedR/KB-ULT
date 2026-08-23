"""The parse -> chunk handoff.

Two rules are pinned here.

**Splitting never crosses a document boundary, and every piece keeps its source document's
locator.** That is the whole reason handlers emit one `Document` per page/slide/section
instead of one blob — it is what makes a chunk citable.

**Every searchable chunk has a parent section.** Retrieval matches the small child and then
reads the parent, so a child without a parent is a chunk that can be found but not
understood. Parents themselves are never embedded and never shown as passages.
"""

from unittest import IsolatedAsyncioTestCase
from uuid import uuid4

from langchain_core.documents import Document

from src.domain.entities import AssetStatus, ChunkModality, KnowledgeAsset
from src.infrastructure.langchain_adapters.text_splitter import RecursiveSplitterAdapter
from src.processing.chunking import StructureAwareChunker


def _asset(documents: list[Document], source_type: str = "pdf") -> KnowledgeAsset:
    return KnowledgeAsset(
        id=uuid4(),
        knowledge_base_id=uuid4(),
        lineage_id=uuid4(),
        filename="report.pdf",
        title="Report",
        source_type=source_type,
        status=AssetStatus.EXTRACTING,
        documents=documents,
    )


def _chunker(chunk_size: int = 800, overlap: int = 120) -> StructureAwareChunker:
    # No LLM: enrichment is exercised separately, and every other property here is about
    # structure, which must hold whether or not a describing model is configured.
    return StructureAwareChunker(RecursiveSplitterAdapter(chunk_size, overlap), enrich=False)


def _leaves(chunks):
    return [chunk for chunk in chunks if not chunk.is_parent]


class ChunkerTest(IsolatedAsyncioTestCase):
    async def test_each_document_keeps_its_locator(self) -> None:
        chunks = await _chunker().chunk(
            _asset(
                [
                    Document(page_content="Page one.", metadata={"locator": {"type": "page", "value": 1}}),
                    Document(page_content="Page two.", metadata={"locator": {"type": "page", "value": 2}}),
                ]
            )
        )

        self.assertEqual([chunk.text for chunk in _leaves(chunks)], ["Page one.", "Page two."])
        self.assertEqual(
            [chunk.metadata["locator"] for chunk in _leaves(chunks)],
            [{"type": "page", "value": 1}, {"type": "page", "value": 2}],
        )

    async def test_an_oversized_document_splits_but_every_piece_keeps_one_locator(self) -> None:
        # A single page far past the token budget. It must become several chunks, and all
        # of them must still cite page 7 — a chunk can never straddle two pages.
        long_page = ". ".join(f"Sentence number {n} about the quarterly results" for n in range(400))
        chunks = await _chunker(chunk_size=100, overlap=10).chunk(
            _asset(
                [Document(page_content=long_page, metadata={"locator": {"type": "page", "value": 7}})]
            )
        )

        self.assertGreater(len(_leaves(chunks)), 1)
        for chunk in chunks:
            self.assertEqual(chunk.metadata["locator"], {"type": "page", "value": 7})

    async def test_chunk_index_is_contiguous_across_documents(self) -> None:
        chunks = await _chunker(chunk_size=50, overlap=5).chunk(
            _asset(
                [
                    Document(page_content=" ".join(["alpha"] * 200), metadata={"locator": {"type": "slide", "value": 1}}),
                    Document(page_content=" ".join(["beta"] * 200), metadata={"locator": {"type": "slide", "value": 2}}),
                ]
            )
        )

        # Indexes run 0..n-1 over every row the asset produces, parents included — the
        # `uq_chunk_asset_index` constraint covers the whole table, not just the leaves.
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))

    async def test_blank_documents_produce_no_chunks(self) -> None:
        # A PDF's blank page arrives as an empty Document. It must not become an empty
        # chunk: that would cost an embedding call and could never match anything.
        chunks = await _chunker().chunk(
            _asset(
                [
                    Document(page_content="   \n  ", metadata={"locator": {"type": "page", "value": 1}}),
                    Document(page_content="Real text.", metadata={"locator": {"type": "page", "value": 2}}),
                ]
            )
        )

        self.assertEqual([chunk.text for chunk in _leaves(chunks)], ["Real text."])
        self.assertEqual(_leaves(chunks)[0].metadata["locator"], {"type": "page", "value": 2})

    async def test_an_asset_with_no_documents_produces_no_chunks(self) -> None:
        # What a pre-migration row looks like on a retry; the pipeline reads this as
        # "re-extract" rather than indexing nothing.
        self.assertEqual(await _chunker().chunk(_asset([])), [])

    async def test_chunk_metadata_carries_the_asset_identity(self) -> None:
        asset = _asset(
            [Document(page_content="Body.", metadata={"locator": {"type": "page", "value": 1}})]
        )

        chunk = _leaves(await _chunker().chunk(asset))[0]

        self.assertEqual(chunk.knowledge_asset_id, asset.id)
        self.assertEqual(chunk.metadata["filename"], "report.pdf")
        self.assertEqual(chunk.metadata["title"], "Report")
        self.assertEqual(chunk.metadata["source_type"], "pdf")
        self.assertEqual(chunk.metadata["knowledge_asset_id"], str(asset.id))


class StructureTest(IsolatedAsyncioTestCase):
    async def test_markdown_headings_become_section_boundaries(self) -> None:
        # PyMuPDF4LLM emits headings inside each page's markdown. Splitting on them means a
        # boundary lands between two ideas rather than in the middle of one.
        page = (
            "# Termination\nEither party may terminate with notice.\n\n"
            "# Payment\nInvoices are due in 30 days.\n"
        )
        chunks = await _chunker().chunk(
            _asset([Document(page_content=page, metadata={"locator": {"type": "page", "value": 4}})])
        )

        headings = [chunk.metadata["heading"] for chunk in chunks if chunk.is_parent]
        self.assertEqual(headings, ["Termination", "Payment"])

    async def test_every_child_points_at_a_parent_that_contains_it(self) -> None:
        page = "# Scope\n" + " ".join(["clause"] * 400)
        chunks = await _chunker(chunk_size=60, overlap=5).chunk(
            _asset([Document(page_content=page, metadata={"locator": {"type": "page", "value": 1}})])
        )

        parents = {chunk.id: chunk for chunk in chunks if chunk.is_parent}
        children = _leaves(chunks)

        self.assertTrue(children)
        for child in children:
            self.assertIn(child.parent_id, parents)
            # The child's text really is part of its parent — this is what makes
            # "expand to the parent" a safe substitution at generation time.
            self.assertIn(child.text[:40], parents[child.parent_id].text)

    async def test_a_section_is_capped_so_a_parent_cannot_be_the_whole_document(self) -> None:
        # No headings at all: without a ceiling the entire document would become one parent,
        # and expanding a match would mean sending all of it to the model.
        huge = " ".join(["word"] * 20000)
        chunks = await _chunker(chunk_size=200, overlap=10).chunk(
            _asset([Document(page_content=huge, metadata={"locator": {"type": "page", "value": 1}})])
        )

        parents = [chunk for chunk in chunks if chunk.is_parent]
        self.assertGreater(len(parents), 1)
        for parent in parents:
            self.assertLessEqual(len(parent.text), 6000)


class ModalityTest(IsolatedAsyncioTestCase):
    async def test_transcripts_are_tagged_asr_and_documents_are_not(self) -> None:
        # The tag is what lets retrieval hold noisy speech-to-text to a different relevance
        # floor than typed prose.
        doc = [Document(page_content="Spoken words.", metadata={"locator": {"type": "timestamp", "value": 12}})]

        audio = await _chunker().chunk(_asset(doc, source_type="audio"))
        youtube = await _chunker().chunk(_asset(doc, source_type="youtube"))
        pdf = await _chunker().chunk(_asset(doc, source_type="pdf"))
        markdown = await _chunker().chunk(_asset(doc, source_type="markdown"))

        self.assertEqual(audio[0].modality, ChunkModality.ASR.value)
        self.assertEqual(youtube[0].modality, ChunkModality.ASR.value)
        self.assertEqual(pdf[0].modality, ChunkModality.PDF.value)
        self.assertEqual(markdown[0].modality, ChunkModality.TEXT.value)

    async def test_an_unknown_source_type_degrades_to_text(self) -> None:
        chunks = await _chunker().chunk(
            _asset([Document(page_content="Body.", metadata={})], source_type="something-new")
        )

        self.assertEqual(chunks[0].modality, ChunkModality.TEXT.value)


class EnrichmentTest(IsolatedAsyncioTestCase):
    class _StubLLM:
        def __init__(self, answer: str = "This is from the termination clause of the Q3 contract.") -> None:
            self.answer = answer
            self.calls = 0

        async def generate(self, messages):
            self.calls += 1
            return self.answer

    async def test_children_embed_with_their_section_context_but_display_plain_text(self) -> None:
        llm = self._StubLLM()
        chunker = StructureAwareChunker(RecursiveSplitterAdapter(60, 5), llm_provider=llm)
        body = "# Termination\n" + " ".join(["clause"] * 300)

        chunks = await chunker.chunk(
            _asset([Document(page_content=body, metadata={"locator": {"type": "page", "value": 2}})])
        )

        child = _leaves(chunks)[0]
        # What gets vectorised carries the context; what gets shown and cited does not.
        self.assertIn("termination clause", child.text_for_embedding)
        self.assertNotIn("termination clause of the Q3", child.text)
        self.assertEqual(child.text_for_embedding.split("\n\n", 1)[1], child.text)

    async def test_the_describing_model_is_called_once_per_section_not_per_chunk(self) -> None:
        # The cost argument for enriching sections rather than chunks: a long document is
        # hundreds of chunks but only a handful of sections.
        llm = self._StubLLM()
        chunker = StructureAwareChunker(RecursiveSplitterAdapter(50, 5), llm_provider=llm)
        body = "# One\n" + " ".join(["alpha"] * 300) + "\n\n# Two\n" + " ".join(["beta"] * 300)

        chunks = await chunker.chunk(
            _asset([Document(page_content=body, metadata={"locator": {"type": "page", "value": 1}})])
        )

        sections = sum(1 for chunk in chunks if chunk.is_parent)
        self.assertEqual(llm.calls, sections)
        self.assertLess(llm.calls, len(_leaves(chunks)))

    async def test_a_failing_describer_does_not_fail_ingestion(self) -> None:
        # Enrichment is an optimisation. If the model is down the chunk embeds as itself,
        # which is exactly the behaviour that predates this feature.
        class _Broken:
            async def generate(self, messages):
                raise RuntimeError("gateway down")

        chunker = StructureAwareChunker(RecursiveSplitterAdapter(60, 5), llm_provider=_Broken())
        chunks = await chunker.chunk(
            _asset([Document(page_content="# Scope\n" + " ".join(["word"] * 100), metadata={})])
        )

        child = _leaves(chunks)[0]
        self.assertTrue(chunks)
        self.assertEqual(child.text_for_embedding, child.text)
