from unittest import TestCase
from unittest.mock import Mock
from uuid import uuid4

from langchain_core.documents import Document

from src.domain.entities import AssetStatus, KnowledgeAsset, SourceType
from src.infrastructure.ai_providers.transcription import Transcript
from src.ingestion.handlers import AudioSourceHandler
from src.ingestion.source_types import source_type_for_filename


class SourceTypeForAudioTest(TestCase):
    def test_resolves_audio_extensions(self) -> None:
        for filename in ["talk.mp3", "talk.m4a", "talk.wav", "talk.ogg", "talk.webm"]:
            self.assertIs(source_type_for_filename(filename), SourceType.AUDIO)


def _asset(filename: str = "board-call.mp3") -> KnowledgeAsset:
    return KnowledgeAsset(
        id=uuid4(),
        knowledge_base_id=uuid4(),
        lineage_id=uuid4(),
        filename=filename,
        source_type="audio",
        storage_key=f"anonymous/{uuid4()}/{filename}",
        status=AssetStatus.QUEUED,
        metadata={"filename": filename, "source_type": "audio"},
    )


class _StubTranscriber:
    """Constructor seam, the same shape the YouTube handler's fetchers use."""

    def __init__(self, transcript: Transcript) -> None:
        self.transcript = transcript
        self.calls: list[tuple[bytes, str]] = []

    def transcribe(self, data: bytes, filename: str) -> Transcript:
        self.calls.append((data, filename))
        return self.transcript


def _handler(transcript: Transcript) -> tuple[AudioSourceHandler, Mock, _StubTranscriber]:
    storage = Mock()
    storage.download.return_value = b"fake-audio-bytes"
    transcriber = _StubTranscriber(transcript)
    return AudioSourceHandler(storage, transcriber), storage, transcriber


class AudioSourceHandlerTest(TestCase):
    def test_acquire_downloads_then_transcribes(self) -> None:
        handler, storage, transcriber = _handler(Transcript(text="Hello there", timed_lines=[]))
        asset = _asset()

        raw = handler.acquire(asset)

        storage.download.assert_called_once_with(asset.storage_key)
        self.assertEqual(transcriber.calls[0][1], "board-call.mp3")
        self.assertEqual(raw.mime, "application/json")

    def test_acquire_rejects_audio_with_no_speech(self) -> None:
        handler, _, _ = _handler(Transcript(text="   ", timed_lines=[]))

        with self.assertRaises(ValueError) as caught:
            handler.acquire(_asset())

        self.assertIn("No speech", str(caught.exception))

    def test_timed_lines_become_timestamp_locators(self) -> None:
        handler, _, _ = _handler(
            Transcript(
                text="first line second line",
                timed_lines=[
                    {"text": "first line", "start": 12.4},
                    {"text": "second line", "start": 14.4},
                ],
                duration=31.2,
            )
        )
        asset = _asset()

        parsed = handler.parse(asset, handler.acquire(asset))

        self.assertEqual(parsed.status, AssetStatus.EXTRACTING)
        self.assertEqual(
            parsed.documents,
            [
                Document(
                    page_content="first line second line",
                    metadata={"locator": {"type": "timestamp", "value": 12}},
                )
            ],
        )
        self.assertEqual(parsed.metadata["duration"], 31)
        self.assertNotIn("timestamps", parsed.metadata)

    def test_untimed_transcript_degrades_to_part_sections(self) -> None:
        # The chat-completions fallback returns flat text. Rather than invent timestamps,
        # the handler emits section locators and flags that timings are unavailable.
        handler, _, _ = _handler(
            Transcript(text="We opened the meeting. Then we closed it.", timed_lines=[])
        )
        asset = _asset()

        parsed = handler.parse(asset, handler.acquire(asset))

        locators = [document.metadata["locator"] for document in parsed.documents]
        self.assertEqual(locators, [{"type": "section", "value": "Part 1"}])
        self.assertEqual(parsed.metadata["timestamps"], "unavailable")

    def test_transcript_is_written_next_to_the_original(self) -> None:
        handler, storage, _ = _handler(
            Transcript(text="Hello", timed_lines=[{"text": "Hello", "start": 0.0}])
        )
        asset = _asset()

        parsed = handler.parse(asset, handler.acquire(asset))

        expected_key = f"{asset.storage_key.rsplit('/', 1)[0]}/transcript.md"
        self.assertEqual(parsed.metadata["transcript_key"], expected_key)
        key, body, content_type = storage.upload.call_args[0]
        self.assertEqual(key, expected_key)
        self.assertEqual(content_type, "text/markdown")
        self.assertIn("## 0:00", body.decode("utf-8"))

    def test_a_failed_transcript_upload_does_not_fail_the_source(self) -> None:
        handler, storage, _ = _handler(
            Transcript(text="Hello", timed_lines=[{"text": "Hello", "start": 0.0}])
        )
        storage.upload.side_effect = RuntimeError("object storage is down")
        asset = _asset()

        parsed = handler.parse(asset, handler.acquire(asset))

        # The source is still usable; it just has no downloadable transcript.
        self.assertNotIn("transcript_key", parsed.metadata)
        self.assertTrue(parsed.documents)

    def test_title_falls_back_to_the_filename_stem(self) -> None:
        handler, _, _ = _handler(Transcript(text="Hello", timed_lines=[]))
        asset = _asset("q3-board-call.mp3")

        parsed = handler.parse(asset, handler.acquire(asset))

        self.assertEqual(parsed.title, "q3-board-call")
