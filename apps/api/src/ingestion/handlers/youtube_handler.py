from __future__ import annotations

import json
import time
from typing import Any, Callable

from src.core.text import sanitize_text_for_storage
from src.domain.entities import AssetStatus, KnowledgeAsset, RawContent
from src.ingestion.handlers._segments import coalesce_timed_lines

# Callable seams so tests can stub network I/O and the exact youtube-transcript-api call
# (its surface shifted between 0.6.x and 1.x) lives in one place.
TranscriptFetcher = Callable[[str], list[dict]]
TitleFetcher = Callable[[str], str | None]

# Tried in order. If none are present we fall back to whatever the video does have rather
# than reporting "no transcript" for a video that simply isn't in English.
PREFERRED_LANGUAGES = ("en", "en-US", "en-GB")

# YouTube's blocking is partly probabilistic, so one cheap retry converts some hard
# failures. It cannot help a wholesale IP-range block — see `_describe_fetch_error`.
BLOCKED_RETRY_DELAY_SECONDS = 1.5


class TranscriptUnavailable(ValueError):
    """A transcript could not be fetched, with a message already fit to show a user.

    Subclasses ValueError because that is what the ingestion pipeline already treats as a
    "this source is bad" signal (vs. an infrastructure crash) — see `acquire`.
    """


def build_transcript_fetcher() -> TranscriptFetcher:
    """Build the real network fetcher.

    Kept as a factory rather than a bare function so tests can substitute the seam, and so
    the exact youtube-transcript-api surface stays in this one module.
    """

    def fetch(video_id: str) -> list[dict]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                # A fresh client per attempt: the library documents `YouTubeTranscriptApi`
                # as not thread-safe, since it owns a requests.Session.
                api = _build_api()
                return _fetch_best_transcript(api, video_id)
            except Exception as exc:  # noqa: BLE001 - re-raised below, classified
                last_error = exc
                if attempt == 0 and _is_blocked(exc):
                    time.sleep(BLOCKED_RETRY_DELAY_SECONDS)
                    continue
                break
        assert last_error is not None  # only reachable via the except branch
        raise TranscriptUnavailable(_describe_fetch_error(last_error)) from last_error

    return fetch


def _build_api() -> Any:
    from youtube_transcript_api import YouTubeTranscriptApi

    return YouTubeTranscriptApi()


def _fetch_best_transcript(api: Any, video_id: str) -> list[dict]:
    """Prefer English, then anything the video actually has.

    `api.fetch()` defaults to English-only and raises `NoTranscriptFound` for, say, a
    Hindi-captioned video — which reads to the user as "no captions" when captions exist.
    Listing first and falling back keeps non-English videos ingestible.
    """
    from youtube_transcript_api import NoTranscriptFound

    transcript_list = api.list(video_id)
    try:
        transcript = transcript_list.find_transcript(PREFERRED_LANGUAGES)
    except NoTranscriptFound:
        available = list(transcript_list)
        if not available:
            raise
        transcript = available[0]
    return transcript.fetch().to_raw_data()


def _is_blocked(exc: Exception) -> bool:
    from youtube_transcript_api import RequestBlocked

    # IpBlocked subclasses RequestBlocked, so this covers both.
    return isinstance(exc, RequestBlocked)


def _describe_fetch_error(exc: Exception) -> str:
    """Turn a youtube-transcript-api exception into something worth showing a user.

    This is the only place that knows the library's exception hierarchy. The result
    becomes the job's `last_error`, which the UI renders next to the retry button — so
    each message says what went wrong *and* what the reader can do about it.
    """
    from youtube_transcript_api import (
        AgeRestricted,
        InvalidVideoId,
        NoTranscriptFound,
        PoTokenRequired,
        RequestBlocked,
        TranscriptsDisabled,
        VideoUnavailable,
        VideoUnplayable,
    )

    if isinstance(exc, (RequestBlocked, PoTokenRequired)):
        # YouTube blocks datacenter IP ranges, so this is normal on a deployed server and
        # nothing the reader did wrong. The audio route genuinely works and produces the
        # same timestamped citations, so it is offered rather than a dead end.
        return (
            "YouTube is blocking transcript requests from this server. Download the "
            "video's audio and upload it as an audio source instead — you'll get the same "
            "timestamped citations."
        )
    if isinstance(exc, TranscriptsDisabled):
        return "This video has captions turned off, so there is no transcript to read."
    if isinstance(exc, NoTranscriptFound):
        return "This video has no transcript available in any language."
    if isinstance(exc, AgeRestricted):
        return "This video is age-restricted, so its transcript cannot be fetched."
    if isinstance(exc, (VideoUnavailable, InvalidVideoId)):
        return "This video is unavailable — it may be private, deleted, or the link may be wrong."
    if isinstance(exc, VideoUnplayable):
        return "YouTube will not play this video, so its transcript cannot be fetched."
    return f"Could not fetch YouTube transcript: {exc}"


_default_transcript_fetcher = build_transcript_fetcher()


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
        except TranscriptUnavailable:
            # Already carries a user-facing message from `_describe_fetch_error`; wrapping
            # it again would bury the actionable part behind a generic prefix.
            raise
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

        segments = coalesce_timed_lines(transcript)
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

