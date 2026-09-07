"""The chunk round-trip: what the chunker builds must survive the database.

This file exists because of a defect it would have caught. Migration 0009 added
`parent_id`, `embed_text` and `modality` to `chunks`; `StructureAwareChunker` set all
three; and neither `replace_for_asset` nor `chunk_to_domain` carried them. Since
`IngestionService` rebinds its chunk list to the round-tripped result before embedding,
every chunk came back with `parent_id = None`, every chunk therefore looked like a parent,
`searchable` was empty, and `embed_texts([])` embedded nothing. The asset still reached
READY. No exception, no log line, no test failure.

The suite missed it for a specific reason worth not repeating: the ingestion test fakes
`replace_for_asset` as `lambda _, chunks: chunks`, which returns the input untouched. The
fake differed from the real repository *only* in the bug. So the tests here exercise the
real mapper and the real model construction, and the round-trip test at the bottom asserts
the one property the fake silently guaranteed.
"""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from uuid import uuid4

from langchain_core.documents import Document

from src.domain.entities import AssetStatus, Chunk, ChunkModality, KnowledgeAsset
from src.infrastructure.langchain_adapters.text_splitter import RecursiveSplitterAdapter
from src.infrastructure.repositories.mappers import chunk_to_domain
from src.infrastructure.repositories.postgres_chunk_repository import ChunkRepository
from src.processing.chunking import StructureAwareChunker


class _FakeSession:
    """Records what the repository would write, without a database.

    `refresh` is a no-op and `scalars` is unused here: the point is the SQLAlchemy model
    objects handed to `add`, which is where the three columns were being dropped.
    """

    def __init__(self) -> None:
        self.added: list = []
        self.executed: list = []
        # `commit_or_flush` reads this to decide whether an enclosing `unit_of_work` owns
        # the transaction. Empty means "commit standalone", which is what ingestion does.
        self.info: dict = {}

    async def execute(self, statement):
        self.executed.append(statement)
        return None

    def add(self, model) -> None:
        self.added.append(model)

    async def refresh(self, model) -> None:
        return None

    async def scalars(self, statement):
        self.executed.append(statement)
        raise AssertionError("no query expected")

    async def commit(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    def in_transaction(self) -> bool:
        return False


def _asset(documents: list[Document]) -> KnowledgeAsset:
    return KnowledgeAsset(
        id=uuid4(),
        knowledge_base_id=uuid4(),
        lineage_id=uuid4(),
        filename="handbook.pdf",
        title="Handbook",
        source_type="pdf",
        status=AssetStatus.EXTRACTING,
        documents=documents,
    )


def _sectioned_asset() -> KnowledgeAsset:
    return _asset(
        [
            Document(
                page_content=(
                    "# Termination\n"
                    "Either party may terminate on thirty days written notice. "
                    "Fees already invoiced remain payable in full.\n"
                    "# Fees and Payment\n"
                    "Enterprise is billed annually at a per-seat rate with a "
                    "twenty-five seat minimum."
                ),
                metadata={"locator": {"type": "page", "value": 12}},
            )
        ]
    )


class WritePathTest(IsolatedAsyncioTestCase):
    async def test_replace_for_asset_persists_the_hierarchy_columns(self) -> None:
        session = _FakeSession()
        repo = ChunkRepository(session)
        asset_id = uuid4()
        parent = Chunk(chunk_index=0, text="A section", modality=ChunkModality.PDF.value)
        child = Chunk(
            chunk_index=1,
            text="A passage",
            parent_id=parent.id,
            embed_text="This section covers fees.\n\nA passage",
            modality=ChunkModality.PDF.value,
        )

        await repo.replace_for_asset(asset_id, [parent, child])

        written_parent, written_child = session.added
        self.assertIsNone(written_parent.parent_id)
        self.assertEqual(written_child.parent_id, parent.id)
        self.assertEqual(written_child.embed_text, "This section covers fees.\n\nA passage")
        self.assertEqual(written_child.modality, ChunkModality.PDF.value)
        self.assertEqual(written_parent.modality, ChunkModality.PDF.value)

    async def test_a_parent_is_written_before_its_children(self) -> None:
        # The self-FK is satisfied by emission order rather than by sorting the INSERTs,
        # so the order the repository hands to `add` is load-bearing.
        session = _FakeSession()
        parent = Chunk(chunk_index=0, text="A section")
        child = Chunk(chunk_index=1, text="A passage", parent_id=parent.id)

        await ChunkRepository(session).replace_for_asset(uuid4(), [parent, child])

        ids = [model.id for model in session.added]
        self.assertLess(ids.index(parent.id), ids.index(child.id))

    async def test_empty_embed_text_is_stored_as_null(self) -> None:
        # Parents, and anything ingested with enrichment off, carry "". The column is
        # nullable and `text_for_embedding` treats both as falsy, so NULL is the honest
        # representation of "nothing to add".
        session = _FakeSession()
        await ChunkRepository(session).replace_for_asset(
            uuid4(), [Chunk(chunk_index=0, text="A section", embed_text="")]
        )
        self.assertIsNone(session.added[0].embed_text)


class ReadPathTest(TestCase):
    def test_chunk_to_domain_restores_the_hierarchy_columns(self) -> None:
        parent_id = uuid4()
        model = SimpleNamespace(
            id=uuid4(),
            knowledge_asset_id=uuid4(),
            chunk_index=3,
            text="A passage",
            metadata_={"filename": "handbook.pdf"},
            created_at=None,
            parent_id=parent_id,
            embed_text="Context.\n\nA passage",
            modality=ChunkModality.ASR.value,
        )

        chunk = chunk_to_domain(model)

        self.assertEqual(chunk.parent_id, parent_id)
        self.assertEqual(chunk.embed_text, "Context.\n\nA passage")
        self.assertEqual(chunk.modality, ChunkModality.ASR.value)
        self.assertFalse(chunk.is_parent)
        self.assertEqual(chunk.text_for_embedding, "Context.\n\nA passage")

    def test_null_embed_text_becomes_the_empty_string(self) -> None:
        chunk = chunk_to_domain(
            SimpleNamespace(
                id=uuid4(),
                knowledge_asset_id=uuid4(),
                chunk_index=0,
                text="A section",
                metadata_=None,
                created_at=None,
                parent_id=None,
                embed_text=None,
                modality=ChunkModality.TEXT.value,
            )
        )
        self.assertEqual(chunk.embed_text, "")
        self.assertTrue(chunk.is_parent)
        # Falls back to the plain text, which is what makes the same call site correct
        # whether or not enrichment ran.
        self.assertEqual(chunk.text_for_embedding, "A section")


class RoundTripTest(IsolatedAsyncioTestCase):
    async def test_chunker_output_survives_persistence_and_stays_embeddable(self) -> None:
        """The assertion whose absence let the defect ship.

        `IngestionService` rebinds `chunks` to whatever `replace_for_asset` returns and
        then filters it to non-parents. If the round trip loses `parent_id`, that filter
        is empty and nothing is ever embedded.
        """
        chunker = StructureAwareChunker(RecursiveSplitterAdapter(120, 20), enrich=False)
        chunks = await chunker.chunk(_sectioned_asset())
        self.assertTrue([c for c in chunks if not c.is_parent], "chunker produced no children")

        session = _FakeSession()
        await ChunkRepository(session).replace_for_asset(uuid4(), chunks)
        round_tripped = [chunk_to_domain(model) for model in session.added]

        searchable = [chunk for chunk in round_tripped if not chunk.is_parent]
        self.assertTrue(searchable, "the round trip lost the hierarchy: nothing would embed")
        self.assertEqual(len(searchable), len([c for c in chunks if not c.is_parent]))
        self.assertTrue(all(chunk.modality == ChunkModality.PDF.value for chunk in searchable))

    async def test_list_parents_of_nothing_issues_no_query(self) -> None:
        # `_expand` calls this whenever any document carries a parent id; an empty list
        # must not become `IN ()`. The fake raises on `scalars`, so a query fails the test.
        self.assertEqual(await ChunkRepository(_FakeSession()).list_parents([]), {})
