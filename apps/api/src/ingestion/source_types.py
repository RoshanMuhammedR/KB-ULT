from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.domain.entities import SourceType

# Maps a file extension to its source type. This is the *edge* resolver: the only
# place a filename/extension is turned into a SourceType. Everything downstream keys
# off SourceType, so a URL-based source (website/youtube) will get its own resolver
# (`source_type_for_url`) here without disturbing the rest of the pipeline.
_EXTENSION_TO_SOURCE_TYPE: dict[str, SourceType] = {
    ".pdf": SourceType.PDF,
}


def source_type_for_filename(filename: str) -> SourceType:
    """Resolve an uploaded file's `SourceType` from its extension.

    Raised as `ValueError` (surfaced as HTTP 400) when the extension is unsupported,
    so the upload request fails fast before anything is stored or enqueued.
    """
    extension = Path(filename).suffix.lower()
    try:
        return _EXTENSION_TO_SOURCE_TYPE[extension]
    except KeyError as exc:
        supported = ", ".join(sorted(_EXTENSION_TO_SOURCE_TYPE)) or "(none)"
        raise ValueError(
            f"Unsupported file type '{extension or filename}'. Supported: {supported}"
        ) from exc


# YouTube host suffixes we accept. Matching by suffix covers www./m./music. subdomains.
_YOUTUBE_HOSTS = ("youtube.com", "youtu.be")


def source_type_for_url(url: str) -> SourceType:
    """Resolve a URL to its `SourceType`. The edge resolver for URL-based sources.

    Mirrors `source_type_for_filename`'s fail-fast contract: a URL we can't handle
    raises `ValueError` (HTTP 400) before anything is persisted. Only YouTube is wired
    today; a website branch slots in here later.
    """
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if host.endswith(_YOUTUBE_HOSTS) or host in _YOUTUBE_HOSTS:
        return SourceType.YOUTUBE
    raise ValueError(f"Unsupported URL '{url}'. Supported sources: youtube")


def identity_for_url(source_type: SourceType, url: str) -> tuple[str, str, dict]:
    """Derive an asset identity from a URL without fetching anything.

    Returns `(filename, source_uri, extra)` where `filename` is the stable dedup/display
    key (so re-ingesting the same video bumps the version, like re-uploading a file),
    `source_uri` is the canonical URL the worker will fetch, and `extra` carries
    source-specific metadata (e.g. the YouTube video id) for the handler's `acquire`.

    Kept pure and fetch-free so it can run in the request path; the heavy work stays in
    the handler's `acquire`.
    """
    if source_type is SourceType.YOUTUBE:
        video_id = _youtube_video_id(url)
        canonical = f"https://www.youtube.com/watch?v={video_id}"
        return video_id, canonical, {"video_id": video_id}
    raise ValueError(f"No URL identity rule for source type '{source_type}'")


# Matches the video id in the common YouTube URL forms: watch?v=, youtu.be/, embed/,
# shorts/, live/, v/. Ids are 11 chars of [A-Za-z0-9_-].
_YOUTUBE_ID_RE = re.compile(r"(?:v=|/(?:embed|shorts|live|v)/|youtu\.be/)([A-Za-z0-9_-]{11})")


def _youtube_video_id(url: str) -> str:
    # Prefer the explicit ?v= query param, then fall back to path-based forms.
    parsed = urlparse(url)
    query_v = parse_qs(parsed.query).get("v", [None])[0]
    if query_v and re.fullmatch(r"[A-Za-z0-9_-]{11}", query_v):
        return query_v
    match = _YOUTUBE_ID_RE.search(url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract a YouTube video id from '{url}'")
