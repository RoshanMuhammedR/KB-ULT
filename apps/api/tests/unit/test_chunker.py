"""The parse -> chunk handoff, which nothing covered directly before.

The rule this pins down: **splitting never crosses a document boundary, and every piece
keeps its source document's locator.** That is the whole reason handlers emit one
`Document` per page/slide/section instead of one blob — it is what makes a chunk citable.
"""

from unittest import TestCase
from uuid import uuid4

from langchain_core.documents import Document

from src.domain.entities import AssetStatus, KnowledgeAsset
from src.infrastructure.langchain_adapters.text_splitter import RecursiveSplitterAdapter
from src.processing.chunking import RecursiveKnowledgeAssetChunker


def _asset(documents: list[Document]) -> KnowledgeAsset:
    return KnowledgeAsset(
        id=uuid4(),
        knowledge_base_id=uuid4(),
        lineage_id=uuid4(),
        filename="report.pdf",
        title="Report",
        source_type="pdf",
        status=AssetStatus.EXTRACTING,
        documents=documents,
    )


def _chunker(chunk_size: int = 800, overlap: int = 120) -> RecursiveKnowledgeAssetChunker:
    return RecursiveKnowledgeAssetChunker(RecursiveSplitterAdapter(chunk_size, overlap))


class ChunkerTest(TestCase):
    def test_each_document_keeps_its_locator(self) -> None:
        chunks = _chunker().chunk(
            _asset(
                [
                    Document(page_content="Page one.", metadata={"locator": {"type": "page", "value": 1}}),
                    Document(page_content="Page two.", metadata={"locator": {"type": "page", "value": 2}}),
                ]
            )
        )

        self.assertEqual([chunk.text for chunk in chunks], ["Page one.", "Page two."])
        self.assertEqual(
            [chunk.metadata["locator"] for chunk in chunks],
            [{"type": "page", "value": 1}, {"type": "page", "value": 2}],
        )

    def test_an_oversized_document_splits_but_every_piece_keeps_one_locator(self) -> None:
        # A single page far past the token budget. It must become several chunks, and all
        # of them must still cite page 7 — a chunk can never straddle two pages.
        long_page = ". ".join(f"Sentence number {n} about the quarterly results" for n in range(400))
        chunks = _chunker(chunk_size=100, overlap=10).chunk(
            _asset(
                [Document(page_content=long_page, metadata={"locator": {"type": "page", "value": 7}})]
            )
        )

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertEqual(chunk.metadata["locator"], {"type": "page", "value": 7})

    def test_chunk_index_is_contiguous_across_documents(self) -> None:
        chunks = _chunker(chunk_size=50, overlap=5).chunk(
            _asset(
                [
                    Document(page_content=" ".join(["alpha"] * 200), metadata={"locator": {"type": "slide", "value": 1}}),
                    Document(page_content=" ".join(["beta"] * 200), metadata={"locator": {"type": "slide", "value": 2}}),
                ]
            )
        )

        # Indexes run 0..n-1 over the whole asset, not restarting per source document —
        # the `uq_chunk_asset_index` constraint depends on that.
        self.assertEqual([chunk.chunk_index for chunk in chunks], list(range(len(chunks))))

    def test_blank_documents_produce_no_chunks(self) -> None:
        # A PDF's blank page arrives as an empty Document. It must not become an empty
        # chunk: that would cost an embedding call and could never match anything.
        chunks = _chunker().chunk(
            _asset(
                [
                    Document(page_content="   \n  ", metadata={"locator": {"type": "page", "value": 1}}),
                    Document(page_content="Real text.", metadata={"locator": {"type": "page", "value": 2}}),
                ]
            )
        )

        self.assertEqual([chunk.text for chunk in chunks], ["Real text."])
        self.assertEqual(chunks[0].metadata["locator"], {"type": "page", "value": 2})

    def test_an_asset_with_no_documents_produces_no_chunks(self) -> None:
        # What a pre-migration row looks like on a retry; the pipeline reads this as
        # "re-extract" rather than indexing nothing.
        self.assertEqual(_chunker().chunk(_asset([])), [])

    def test_chunk_metadata_carries_the_asset_identity(self) -> None:
        asset = _asset(
            [Document(page_content="Body.", metadata={"locator": {"type": "page", "value": 1}})]
        )

        chunk = _chunker().chunk(asset)[0]

        self.assertEqual(chunk.knowledge_asset_id, asset.id)
        self.assertEqual(chunk.metadata["filename"], "report.pdf")
        self.assertEqual(chunk.metadata["title"], "Report")
        self.assertEqual(chunk.metadata["source_type"], "pdf")
        self.assertEqual(chunk.metadata["knowledge_asset_id"], str(asset.id))
