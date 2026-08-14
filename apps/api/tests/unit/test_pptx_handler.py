from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4

from src.domain.entities import AssetStatus, KnowledgeAsset, SourceType
from src.ingestion.handlers import PptxSourceHandler
from src.ingestion.source_types import source_type_for_filename


class SourceTypeForPptxTest(TestCase):
    def test_resolves_pptx_extension(self) -> None:
        self.assertIs(source_type_for_filename("deck.pptx"), SourceType.PPTX)


def _asset(filename: str = "kickoff.pptx") -> KnowledgeAsset:
    return KnowledgeAsset(
        id=uuid4(),
        knowledge_base_id=uuid4(),
        lineage_id=uuid4(),
        filename=filename,
        source_type="pptx",
        storage_key=f"anonymous/{uuid4()}/{filename}",
        status=AssetStatus.QUEUED,
        metadata={"filename": filename, "source_type": "pptx"},
    )


def _handler(slides, filename: str = "kickoff.pptx") -> PptxSourceHandler:
    storage = Mock()
    storage.download.return_value = b"fake-pptx-bytes"
    # The deck reader is a constructor seam, so no python-pptx or real file is needed.
    return PptxSourceHandler(storage, deck_reader=lambda data: slides)


class PptxSourceHandlerTest(TestCase):
    def test_parse_emits_one_segment_per_slide_with_slide_locators(self) -> None:
        handler = _handler(
            [
                {"number": 1, "title": "Kickoff", "lines": ["Kickoff", "Q3 plan"], "notes": ""},
                {"number": 2, "title": "Risks", "lines": ["Risks", "Supply delays"], "notes": ""},
            ]
        )
        asset = _asset()

        parsed = handler.parse(asset, handler.acquire(asset))

        self.assertEqual(parsed.status, AssetStatus.EXTRACTING)
        self.assertEqual(parsed.title, "Kickoff")
        locators = [segment["locator"] for segment in parsed.metadata["segments"]]
        self.assertEqual(
            locators,
            [{"type": "slide", "value": 1}, {"type": "slide", "value": 2}],
        )
        self.assertEqual(parsed.metadata["slide_count"], 2)
        self.assertEqual(
            parsed.metadata["slides"],
            [{"number": 1, "title": "Kickoff"}, {"number": 2, "title": "Risks"}],
        )

    def test_speaker_notes_are_included_in_the_slide_segment(self) -> None:
        handler = _handler(
            [{"number": 1, "title": "Kickoff", "lines": ["Kickoff"], "notes": "Mention the budget"}]
        )
        asset = _asset()

        parsed = handler.parse(asset, handler.acquire(asset))

        self.assertIn("Mention the budget", parsed.metadata["segments"][0]["text"])

    def test_slides_with_no_text_are_skipped_but_still_counted(self) -> None:
        handler = _handler(
            [
                {"number": 1, "title": "", "lines": [], "notes": ""},
                {"number": 2, "title": "Data", "lines": ["Data"], "notes": ""},
            ]
        )
        asset = _asset()

        parsed = handler.parse(asset, handler.acquire(asset))

        self.assertEqual(len(parsed.metadata["segments"]), 1)
        self.assertEqual(parsed.metadata["segments"][0]["locator"]["value"], 2)
        self.assertEqual(parsed.metadata["slide_count"], 2)

    def test_empty_deck_fails_into_the_retry_path(self) -> None:
        handler = _handler([])
        asset = _asset()

        with self.assertRaises(ValueError) as caught:
            handler.parse(asset, handler.acquire(asset))

        self.assertIn("no slides", str(caught.exception))

    def test_deck_with_no_readable_text_fails(self) -> None:
        handler = _handler([{"number": 1, "title": "", "lines": [], "notes": ""}])
        asset = _asset()

        with self.assertRaises(ValueError) as caught:
            handler.parse(asset, handler.acquire(asset))

        self.assertIn("no readable text", str(caught.exception))

    def test_unreadable_file_is_normalized_to_a_plain_language_error(self) -> None:
        storage = Mock()
        storage.download.return_value = b"not-a-deck"

        def explode(data: bytes):
            raise RuntimeError("package not found")

        handler = PptxSourceHandler(storage, deck_reader=explode)
        asset = _asset()

        with self.assertRaises(ValueError) as caught:
            handler.parse(asset, handler.acquire(asset))

        self.assertIn("could not be opened", str(caught.exception))

    def test_title_falls_back_to_the_filename_stem(self) -> None:
        handler = _handler(
            [{"number": 1, "title": "", "lines": ["Just body text"], "notes": ""}],
        )
        asset = _asset("board-review.pptx")

        parsed = handler.parse(asset, handler.acquire(asset))

        self.assertEqual(parsed.title, "board-review")
