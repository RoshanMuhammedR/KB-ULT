from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from langchain_core.documents import Document
from youtube_transcript_api import (
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
)

from src.domain.entities import AssetStatus, KnowledgeAsset, RawContent, SourceType
from src.ingestion.handlers import YouTubeSourceHandler, build_transcript_fetcher
from src.ingestion.handlers.youtube_handler import TranscriptUnavailable
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

    def test_parse_builds_timestamp_locator_documents(self) -> None:
        # Two short lines under the coalesce target collapse into one document whose
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
            parsed.documents,
            [
                Document(
                    page_content="first line second line",
                    metadata={"locator": {"type": "timestamp", "value": 12}},
                )
            ],
        )

    def test_parse_splits_into_windows_past_char_target(self) -> None:
        # Long lines exceed the coalesce target, so each becomes its own document with
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

        locators = [doc.metadata["locator"]["value"] for doc in parsed.documents]
        self.assertEqual(locators, [0, 60])

    def test_acquire_passes_through_the_user_facing_message(self) -> None:
        # A TranscriptUnavailable already carries a message written for a reader, so
        # `acquire` must not bury it behind the generic "Could not fetch..." prefix.
        def blocked(video_id: str) -> list[dict]:
            raise TranscriptUnavailable("YouTube is blocking transcript requests")

        handler = YouTubeSourceHandler(transcript_fetcher=blocked, title_fetcher=lambda url: None)
        with self.assertRaises(ValueError) as caught:
            handler.acquire(_asset())
        self.assertEqual(str(caught.exception), "YouTube is blocking transcript requests")


# --- Fetcher fakes ------------------------------------------------------------------
# Stand in for the youtube-transcript-api objects (`TranscriptList` -> `Transcript` ->
# `FetchedTranscript`) so the fetcher's language and error handling can be tested without
# a network call.


class _FakeFetched:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def to_raw_data(self) -> list[dict]:
        return self._rows


class _FakeTranscript:
    def __init__(self, language_code: str, rows: list[dict]) -> None:
        self.language_code = language_code
        self._rows = rows

    def fetch(self) -> _FakeFetched:
        return _FakeFetched(self._rows)


class _FakeTranscriptList:
    def __init__(self, transcripts: list[_FakeTranscript]) -> None:
        self._transcripts = transcripts

    def __iter__(self):
        return iter(self._transcripts)

    def find_transcript(self, language_codes) -> _FakeTranscript:
        for code in language_codes:
            for transcript in self._transcripts:
                if transcript.language_code == code:
                    return transcript
        raise NoTranscriptFound("dQw4w9WgXcQ", list(language_codes), self)


class _FakeApi:
    """Records how many times `list` was called, so retry behaviour is observable."""

    def __init__(self, result) -> None:
        self._result = result
        self.calls = 0

    def list(self, video_id: str):
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class TranscriptFetcherTest(TestCase):
    def _fetch(self, api: _FakeApi) -> list[dict]:
        with patch("src.ingestion.handlers.youtube_handler._build_api", return_value=api):
            return build_transcript_fetcher()("dQw4w9WgXcQ")

    def test_prefers_english_when_present(self) -> None:
        api = _FakeApi(
            _FakeTranscriptList(
                [
                    _FakeTranscript("hi", [{"text": "namaste", "start": 0.0, "duration": 1.0}]),
                    _FakeTranscript("en", [{"text": "hello", "start": 0.0, "duration": 1.0}]),
                ]
            )
        )
        self.assertEqual(self._fetch(api)[0]["text"], "hello")

    def test_falls_back_to_any_language_rather_than_reporting_none(self) -> None:
        # The library's `fetch()` shortcut is English-only and would raise NoTranscriptFound
        # here, which reads to the user as "this video has no captions" when it plainly does.
        api = _FakeApi(
            _FakeTranscriptList(
                [_FakeTranscript("hi", [{"text": "namaste", "start": 0.0, "duration": 1.0}])]
            )
        )
        self.assertEqual(self._fetch(api)[0]["text"], "namaste")

    def test_retries_once_when_blocked_then_gives_up(self) -> None:
        api = _FakeApi(RequestBlocked("dQw4w9WgXcQ"))
        with patch("src.ingestion.handlers.youtube_handler.time.sleep") as sleep:
            with self.assertRaises(TranscriptUnavailable) as caught:
                self._fetch(api)
        self.assertEqual(api.calls, 2)
        sleep.assert_called_once()
        self.assertIn("blocking transcript requests", str(caught.exception))
        self.assertIn("audio source", str(caught.exception))

    def test_does_not_retry_a_permanent_failure(self) -> None:
        api = _FakeApi(TranscriptsDisabled("dQw4w9WgXcQ"))
        with self.assertRaises(TranscriptUnavailable) as caught:
            self._fetch(api)
        self.assertEqual(api.calls, 1)
        self.assertIn("captions turned off", str(caught.exception))

    def test_distinguishes_an_unavailable_video(self) -> None:
        api = _FakeApi(VideoUnavailable("dQw4w9WgXcQ"))
        with self.assertRaises(TranscriptUnavailable) as caught:
            self._fetch(api)
        self.assertIn("unavailable", str(caught.exception))

    def test_reports_no_transcript_when_the_video_truly_has_none(self) -> None:
        api = _FakeApi(_FakeTranscriptList([]))
        with self.assertRaises(TranscriptUnavailable) as caught:
            self._fetch(api)
        self.assertIn("no transcript available", str(caught.exception))
