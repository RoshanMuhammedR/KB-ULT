from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4

from src.domain.entities import AssetStatus, KnowledgeAsset, SourceType
from src.ingestion.handlers import MarkdownSourceHandler
from src.ingestion.source_types import source_type_for_filename


class SourceTypeForMarkdownTest(TestCase):
    def test_resolves_markdown_extensions(self) -> None:
        self.assertIs(source_type_for_filename("notes.md"), SourceType.MARKDOWN)
        self.assertIs(source_type_for_filename("NOTES.MARKDOWN"), SourceType.MARKDOWN)


def _asset(filename: str = "field-notes.md") -> KnowledgeAsset:
    return KnowledgeAsset(
        id=uuid4(),
        knowledge_base_id=uuid4(),
        lineage_id=uuid4(),
        filename=filename,
        source_type="markdown",
        storage_key=f"anonymous/{uuid4()}/{filename}",
        status=AssetStatus.QUEUED,
        metadata={"filename": filename, "source_type": "markdown"},
    )


def _handler(body: str) -> tuple[MarkdownSourceHandler, Mock]:
    storage = Mock()
    storage.download.return_value = body.encode("utf-8")
    return MarkdownSourceHandler(storage), storage


class MarkdownSourceHandlerTest(TestCase):
    def test_acquire_reads_bytes_from_storage(self) -> None:
        handler, storage = _handler("# Title\n\nBody.")
        asset = _asset()

        raw = handler.acquire(asset)

        storage.download.assert_called_once_with(asset.storage_key)
        self.assertEqual(raw.mime, "text/markdown")

    def test_parse_splits_on_headings_into_section_locators(self) -> None:
        handler, _ = _handler(
            "# Field notes\n\nOpening paragraph.\n\n## Method\n\nWe measured twice.\n"
        )
        asset = _asset()

        parsed = handler.parse(asset, handler.acquire(asset))

        self.assertEqual(parsed.status, AssetStatus.EXTRACTING)
        self.assertEqual(parsed.title, "Field notes")
        locators = [segment["locator"] for segment in parsed.metadata["segments"]]
        self.assertEqual(
            locators,
            [
                {"type": "section", "value": "Field notes"},
                {"type": "section", "value": "Method"},
            ],
        )
        self.assertIn("We measured twice.", parsed.metadata["segments"][1]["text"])

    def test_text_before_the_first_heading_becomes_an_introduction(self) -> None:
        handler, _ = _handler("Stray preamble text.\n\n# Later heading\n\nBody.\n")
        asset = _asset()

        parsed = handler.parse(asset, handler.acquire(asset))

        first = parsed.metadata["segments"][0]
        self.assertEqual(first["locator"], {"type": "section", "value": "Introduction"})
        self.assertIn("Stray preamble", first["text"])
        # The title still comes from the first real heading, not the preamble.
        self.assertEqual(parsed.title, "Later heading")

    def test_title_falls_back_to_the_filename_stem(self) -> None:
        handler, _ = _handler("Just a paragraph, no headings at all.\n")
        asset = _asset("meeting-notes.md")

        parsed = handler.parse(asset, handler.acquire(asset))

        self.assertEqual(parsed.title, "meeting-notes")

    def test_empty_file_fails_with_a_plain_language_error(self) -> None:
        handler, _ = _handler("   \n\n  \n")
        asset = _asset()

        with self.assertRaises(ValueError) as caught:
            handler.parse(asset, handler.acquire(asset))

        self.assertIn("no readable text", str(caught.exception))
