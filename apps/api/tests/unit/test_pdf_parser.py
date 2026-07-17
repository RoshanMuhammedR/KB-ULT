from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4

from src.domain.entities import AssetStatus, KnowledgeAsset, RawContent
from src.ingestion.handlers import PdfSourceHandler


class PdfSourceHandlerTest(TestCase):
    def _asset(self) -> KnowledgeAsset:
        return KnowledgeAsset(
            id=uuid4(),
            knowledge_base_id=uuid4(),
            lineage_id=uuid4(),
            version=2,
            filename="sample.pdf",
            source_type="pdf",
            storage_key="user/asset/sample.pdf",
            status=AssetStatus.QUEUED,
            metadata={"content_type": "application/pdf"},
        )

    def test_acquire_downloads_bytes_from_storage(self) -> None:
        file_storage = Mock()
        file_storage.download.return_value = b"%PDF"
        handler = PdfSourceHandler(loader=Mock(), file_storage=file_storage)

        raw = handler.acquire(self._asset())

        self.assertEqual(raw.data, b"%PDF")
        file_storage.download.assert_called_once_with("user/asset/sample.pdf")

    def test_parse_builds_markdown_and_segments(self) -> None:
        loader = SimpleNamespace(
            load=lambda file_data, filename: {
                "markdown": "# Heading\n\n| A | B |",
                "title": "Parsed Title",
                # Docling still returns pages; the handler turns them into segments.
                "pages": [{"page_number": 3, "text": "# Heading\x00"}],
                "metadata": {"status": "success", "errors": 0, "page_count": 1},
            }
        )
        handler = PdfSourceHandler(loader=loader, file_storage=Mock())
        asset = self._asset()

        parsed = handler.parse(asset, RawContent(data=b"%PDF", mime="application/pdf"))

        self.assertEqual(parsed.id, asset.id)
        self.assertEqual(parsed.status, AssetStatus.EXTRACTING)
        self.assertEqual(parsed.title, "Parsed Title")
        self.assertEqual(parsed.text_content, "# Heading\n\n| A | B |")
        self.assertEqual(parsed.metadata["format"], "markdown")
        self.assertEqual(parsed.metadata["source_type"], "pdf")
        # Page number becomes a typed locator; null bytes are sanitized out of text.
        self.assertEqual(
            parsed.metadata["segments"],
            [{"text": "# Heading", "locator": {"type": "page", "value": 3}}],
        )
        self.assertEqual(parsed.metadata["docling"]["status"], "success")
