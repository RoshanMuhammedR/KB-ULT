import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4

sys.modules.setdefault("structlog", SimpleNamespace(get_logger=lambda *_: Mock()))

from src.application.ingestion.service import IngestionService
from src.domain.entities import AssetStatus, Chunk, Embedding, KnowledgeAsset, KnowledgeBase


class IngestionFileStorageTest(TestCase):
    def test_uploads_with_expected_storage_key_before_parsing(self) -> None:
        kb_id = uuid4()
        kb_repo = Mock()
        kb_repo.ensure_default.return_value = KnowledgeBase(id=kb_id)
        asset_repo = Mock()
        asset_repo.latest_for_filename.return_value = None

        def create_pending(asset: KnowledgeAsset) -> KnowledgeAsset:
            return asset

        asset_repo.create_pending.side_effect = create_pending
        asset_repo.update_from_domain.side_effect = lambda asset: asset
        chunk_repo = Mock()
        chunk_repo.replace_for_asset.side_effect = lambda _, chunks: [
            Chunk(id=uuid4(), knowledge_asset_id=chunks[0].knowledge_asset_id, text=chunks[0].text)
        ]
        parser = Mock()
        parser.parse.side_effect = lambda source: KnowledgeAsset(
            id=source.asset_id,
            knowledge_base_id=source.knowledge_base_id,
            lineage_id=source.lineage_id,
            version=source.version,
            filename=source.filename,
            source_type="pdf",
            storage_key=source.storage_key,
            status=AssetStatus.EXTRACTING,
            metadata={"pages": [{"page_number": 1, "text": "hello"}]},
        )
        parser_registry = Mock()
        parser_registry.get.return_value = parser
        chunker = Mock()
        chunker.chunk.return_value = [Chunk(text="hello")]
        embedder = Mock()
        embedder.embed_texts.return_value = [Embedding(vector=[0.1], model="m", dimensions=1)]
        vector_store = Mock()
        file_storage = Mock()
        file_storage.upload.side_effect = lambda key, file_data, content_type: key

        service = IngestionService(
            kb_repo=kb_repo,
            asset_repo=asset_repo,
            chunk_repo=chunk_repo,
            parser_registry=parser_registry,
            chunker=chunker,
            embedding_provider=embedder,
            vector_store=vector_store,
            file_storage=file_storage,
        )

        asset = service.ingest_file(b"pdf", "../ My File.pdf ", "application/pdf", user_id="user-1")

        self.assertEqual(asset.status, AssetStatus.READY)
        self.assertTrue(asset.storage_key.startswith("user-1/"))
        self.assertTrue(asset.storage_key.endswith("/My File.pdf"))
        file_storage.upload.assert_called_once()
        _, kwargs = file_storage.upload.call_args
        self.assertEqual(kwargs["file_data"], b"pdf")
        self.assertEqual(kwargs["content_type"], "application/pdf")
