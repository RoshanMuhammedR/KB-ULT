from types import SimpleNamespace
from unittest import TestCase
from uuid import uuid4

from src.domain.entities import AssetStatus
from src.ingestion.parsers import PDFParser
from src.ingestion.sources.file_source import FileSource


class PDFParserTest(TestCase):
    def test_docling_markdown_becomes_asset_text_content_and_metadata(self) -> None:
        asset_id = uuid4()
        knowledge_base_id = uuid4()
        lineage_id = uuid4()
        loader = SimpleNamespace(
            load=lambda file_data, filename: {
                "markdown": "# Heading\n\n| A | B |",
                "title": "Parsed Title",
                "pages": [{"page_number": 3, "text": "# Heading\x00"}],
                "metadata": {"status": "success", "errors": 0, "page_count": 1},
            }
        )

        asset = PDFParser(loader).parse(
            FileSource(
                asset_id=asset_id,
                file_data=b"%PDF",
                filename="sample.pdf",
                storage_key="user/asset/sample.pdf",
                knowledge_base_id=knowledge_base_id,
                lineage_id=lineage_id,
                version=2,
                content_type="application/pdf",
            )
        )

        self.assertEqual(asset.id, asset_id)
        self.assertEqual(asset.status, AssetStatus.EXTRACTING)
        self.assertEqual(asset.title, "Parsed Title")
        self.assertEqual(asset.text_content, "# Heading\n\n| A | B |")
        self.assertEqual(asset.metadata["format"], "markdown")
        self.assertEqual(asset.metadata["source_type"], "pdf")
        self.assertEqual(asset.metadata["pages"], [{"page_number": 3, "text": "# Heading"}])
        self.assertEqual(asset.metadata["docling"]["status"], "success")
