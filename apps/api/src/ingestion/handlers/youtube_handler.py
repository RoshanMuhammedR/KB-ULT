from __future__ import annotations

import json
from typing import Callable

from src.core.text import sanitize_text_for_storage
from src.domain.entities import AssetStatus, KnowledgeAsset, RawContent

# Coalesce transcript lines into segments of roughly this many characters. YouTube
# transcript entries are tiny (a few words each); grouping them yields citation-friendly
# chunks while the start time of each group becomes the citation locator.
_SEGMENT_CHAR_TARGET = 500

# Callable seams so tests can stub network I/O and the exact youtube-transcript-api call
# (its surface shifted between 0.6.x and 1.x) lives in one place.
TranscriptFetcher = Callable[[str], list[dict]]
TitleFetcher = Callable[[str], str | None]


def _default_transcript_fetcher(video_id: str) -> list[dict]:
    # youtube-transcript-api 1.x is instance-based: fetch() -> FetchedTranscript, whose
    # to_raw_data() yields [{text, start, duration}]. Errors (captions disabled, no
    # transcript, blocked) raise CouldNotRetrieveTranscript, handled in `acquire`.
    from youtube_transcript_api import YouTubeTranscriptApi

    return YouTubeTranscriptApi().fetch(video_id).to_raw_data()


def _default_title_fetcher(url: str) -> str | None:
    # YouTube oEmbed returns the video title with no API key. Best-effort: a failure
    # just falls back to the video id as the title.
    import httpx

    try:
        response = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json().get("title")
    except Exception:  # noqa: BLE001 - title is optional, never fail ingestion over it
        return None


class YouTubeSourceHandler:
    """Source handler for YouTube videos (implements `ISourceHandler`).

    The first URL-based source: there is no uploaded file, so `acquire` fetches the
    transcript live from the video id (re-fetching on retry is idempotent and cheap, so
    nothing is snapshotted to object storage). `parse` turns transcript lines into the
    same source-neutral `segments` the PDF handler emits — the only difference is a
    `timestamp` locator instead of a `page` one, so chunking, embedding, and chat need
    no YouTube-specific code.
    """

    def __init__(
        self,
        transcript_fetcher: TranscriptFetcher = _default_transcript_fetcher,
        title_fetcher: TitleFetcher = _default_title_fetcher,
    ) -> None:
        self.transcript_fetcher = transcript_fetcher
        self.title_fetcher = title_fetcher

    def acquire(self, asset: KnowledgeAsset) -> RawContent:
        video_id = asset.metadata.get("video_id")
        source_uri = asset.metadata.get("source_uri") or f"https://www.youtube.com/watch?v={video_id}"
        if not video_id:
            raise ValueError("YouTube asset is missing its video_id")

        try:
            transcript = self.transcript_fetcher(video_id)
        except Exception as exc:  # noqa: BLE001 - normalize any fetch error to a clear message
            # Surfaced as the job's last_error + a "failed" worker-log event + retry button.
            raise ValueError(f"Could not fetch YouTube transcript: {exc}") from exc
        if not transcript:
            raise ValueError("YouTube video has no transcript/captions available")

        title = self.title_fetcher(source_uri)
        payload = json.dumps({"transcript": transcript, "title": title, "source_uri": source_uri})
        return RawContent(data=payload, mime="application/json")

    def parse(self, asset: KnowledgeAsset, raw: RawContent) -> KnowledgeAsset:
        data = raw.data if isinstance(raw.data, str) else raw.data.decode("utf-8")
        payload = json.loads(data)
        transcript: list[dict] = payload["transcript"]

        segments = self._coalesce(transcript)
        full_text = sanitize_text_for_storage("\n".join(seg["text"] for seg in segments)).strip()
        title = sanitize_text_for_storage(payload.get("title") or asset.filename)

        return KnowledgeAsset(
            id=asset.id,
            knowledge_base_id=asset.knowledge_base_id,
            lineage_id=asset.lineage_id,
            version=asset.version,
            filename=asset.filename,
            title=title,
            source_type=asset.source_type,
            storage_key=asset.storage_key,
            status=AssetStatus.EXTRACTING,
            text_content=full_text,
            metadata={
                "filename": asset.filename,
                "title": title,
                "source_type": asset.source_type,
                "format": "transcript",
                "source_uri": payload.get("source_uri") or asset.metadata.get("source_uri"),
                "video_id": asset.metadata.get("video_id"),
                "segments": segments,
            },
        )

    def _coalesce(self, transcript: list[dict]) -> list[dict]:
        # Group consecutive transcript lines into ~_SEGMENT_CHAR_TARGET windows, keeping
        # each window's first line's start time as its timestamp locator (whole seconds).
        # Flush *before* adding a line that would overflow so windows stay bounded and a
        # large time gap between lines starts a fresh, correctly-timestamped segment.
        segments: list[dict] = []
        buffer: list[str] = []
        window_start = 0.0
        current_len = 0

        for line in transcript:
            text = line.get("text") or ""
            if buffer and current_len + len(text) > _SEGMENT_CHAR_TARGET:
                self._emit(segments, buffer, window_start)
                buffer = []
                current_len = 0
            if not buffer:
                window_start = float(line.get("start", 0) or 0)
            buffer.append(text)
            current_len += len(text)

        self._emit(segments, buffer, window_start)
        return segments

    @staticmethod
    def _emit(segments: list[dict], buffer: list[str], window_start: float) -> None:
        if not buffer:
            return
        text = sanitize_text_for_storage(" ".join(buffer)).strip()
        if text:
            segments.append(
                {"text": text, "locator": {"type": "timestamp", "value": int(window_start)}}
            )
