from unittest import TestCase
from uuid import uuid4

from src.domain.entities import AssetStatus, KnowledgeAsset, RawContent, SourceType
from src.ingestion.handlers import YouTubeSourceHandler
from src.ingestion.source_types import identity_for_url, source_type_for_url


class SourceTypeForUrlTest(TestCase):
    def test_resolves_youtube_url_forms_to_video_id(self) -> None:
        cases = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ?t=30",
            "https://youtube.com/shorts/dQw4w9WgXcQ",
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=abc",
        ]
        for url in cases:
            source_type = source_type_for_url(url)
            self.assertIs(source_type, SourceType.YOUTUBE)
            filename, source_uri, extra = identity_for_url(source_type, url)
            self.assertEqual(extra["video_id"], "dQw4w9WgXcQ")
            self.assertEqual(filename, "dQw4w9WgXcQ")
            self.assertIn("watch?v=dQw4w9WgXcQ", source_uri)

    def test_rejects_non_youtube_url(self) -> None:
        with self.assertRaises(ValueError):
            source_type_for_url("https://example.com/article")


def _asset() -> KnowledgeAsset:
    return KnowledgeAsset(
        id=uuid4(),
        knowledge_base_id=uuid4(),
        lineage_id=uuid4(),
        filename="dQw4w9WgXcQ",
        source_type="youtube",
        storage_key="",
        status=AssetStatus.QUEUED,
        metadata={"video_id": "dQw4w9WgXcQ", "source_uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )


class YouTubeSourceHandlerTest(TestCase):
    def test_acquire_wraps_transcript_and_title(self) -> None:
        handler = YouTubeSourceHandler(
            transcript_fetcher=lambda vid: [{"text": "hello", "start": 0.0, "duration": 1.0}],
            title_fetcher=lambda url: "My Video",
        )
        raw = handler.acquire(_asset())
        self.assertEqual(raw.mime, "application/json")
        self.assertIn("My Video", raw.data)

    def test_acquire_raises_clear_error_when_no_transcript(self) -> None:
        handler = YouTubeSourceHandler(transcript_fetcher=lambda vid: [], title_fetcher=lambda url: None)
        with self.assertRaises(ValueError):
            handler.acquire(_asset())

    def test_parse_builds_timestamp_locator_segments(self) -> None:
        # Two short lines under the coalesce target collapse into one segment whose
        # locator is the first line's start time (whole seconds).
        transcript = [
            {"text": "first line", "start": 12.4, "duration": 2.0},
            {"text": "second line", "start": 14.4, "duration": 2.0},
        ]
        handler = YouTubeSourceHandler(
            transcript_fetcher=lambda vid: transcript,
            title_fetcher=lambda url: "Parsed Title",
        )
        asset = _asset()
        raw = handler.acquire(asset)

        parsed = handler.parse(asset, raw)

        self.assertEqual(parsed.status, AssetStatus.EXTRACTING)
        self.assertEqual(parsed.title, "Parsed Title")
        self.assertEqual(parsed.metadata["format"], "transcript")
        self.assertEqual(parsed.metadata["video_id"], "dQw4w9WgXcQ")
        self.assertEqual(
            parsed.metadata["segments"],
            [{"text": "first line second line", "locator": {"type": "timestamp", "value": 12}}],
        )

    def test_parse_splits_into_windows_past_char_target(self) -> None:
        # Long lines exceed the coalesce target, so each becomes its own segment with
        # its own start timestamp.
        long_a = "a" * 400
        long_b = "b" * 400
        transcript = [
            {"text": long_a, "start": 0.0, "duration": 1.0},
            {"text": long_b, "start": 60.0, "duration": 1.0},
        ]
        handler = YouTubeSourceHandler(
            transcript_fetcher=lambda vid: transcript,
            title_fetcher=lambda url: None,
        )
        asset = _asset()
        parsed = handler.parse(asset, handler.acquire(asset))

        locators = [seg["locator"]["value"] for seg in parsed.metadata["segments"]]
        self.assertEqual(locators, [0, 60])
