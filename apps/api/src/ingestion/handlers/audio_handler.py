from __future__ import annotations

import json
from typing import Protocol

from src.core.text import sanitize_text_for_storage
from src.domain.entities import AssetStatus, KnowledgeAsset, RawContent
from src.domain.interfaces import IFileStorage
from src.infrastructure.ai_providers.transcription import Transcript
from src.ingestion.handlers._segments import coalesce_timed_lines, split_untimed_text

# The transcript is written back next to the original upload under this name, so the app can
# show the full text and the player can be read alongside it.
TRANSCRIPT_FILENAME = "transcript.md"


class ITranscriber(Protocol):
    """Constructor seam — tests stub this rather than the HTTP client."""

    def transcribe(self, data: bytes, filename: str) -> Transcript: ...


class AudioSourceHandler:
    """Source handler for uploaded audio (implements `ISourceHandler`).

    The slowest source by a wide margin: `acquire` downloads the file and transcribes it
    through a hosted model, which takes minutes for a long recording. That is why the UI
    treats audio progress as the case where waiting feedback matters most.

    Locators degrade honestly. When the provider returns per-segment timings we emit
    `timestamp` locators, coalesced by the same helper the YouTube handler uses. When it
    returns only flat text we emit `section` "Part N" locators and set
    `metadata["timestamps"] = "unavailable"`, so the viewer starts the player from the
    beginning instead of claiming a second it cannot justify.
    """

    def __init__(self, file_storage: IFileStorage, transcriber: ITranscriber) -> None:
        self.file_storage = file_storage
        self.transcriber = transcriber

    def acquire(self, asset: KnowledgeAsset) -> RawContent:
        data = self.file_storage.download(asset.storage_key)
        transcript = self.transcriber.transcribe(data, asset.filename)
        if not transcript.text.strip():
            raise ValueError("No speech could be found in this audio file")

        payload = json.dumps(
            {
                "text": transcript.text,
                "segments": transcript.segments,
                "duration": transcript.duration,
            }
        )
        return RawContent(data=payload, mime="application/json")

    def parse(self, asset: KnowledgeAsset, raw: RawContent) -> KnowledgeAsset:
        data = raw.data if isinstance(raw.data, str) else raw.data.decode("utf-8")
        payload = json.loads(data)

        timed_lines: list[dict] = payload.get("segments") or []
        if timed_lines:
            segments = coalesce_timed_lines(timed_lines)
            timestamps_available = True
        else:
            segments = split_untimed_text(payload.get("text") or "")
            timestamps_available = False

        if not segments:
            raise ValueError("No speech could be found in this audio file")

        full_text = sanitize_text_for_storage(payload.get("text") or "").strip()
        if not full_text:
            full_text = "\n".join(segment["text"] for segment in segments)

        title = self._title(asset.filename)
        transcript_key = self._store_transcript(asset, title, segments, timestamps_available)

        metadata: dict = {
            "filename": asset.filename,
            "title": title,
            "source_type": asset.source_type,
            "format": "transcript",
            "content_type": asset.metadata.get("content_type"),
            "segments": segments,
        }
        if payload.get("duration") is not None:
            metadata["duration"] = round(float(payload["duration"]))
        if not timestamps_available:
            metadata["timestamps"] = "unavailable"
        if transcript_key:
            metadata["transcript_key"] = transcript_key

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
            metadata=metadata,
        )

    # --- Transcript file ----------------------------------------------------------

    def _store_transcript(
        self,
        asset: KnowledgeAsset,
        title: str,
        segments: list[dict],
        timestamps_available: bool,
    ) -> str | None:
        """Upload a readable transcript.md beside the original; never fail ingestion over it.

        The transcript is a user-visible artefact, not a pipeline input — the searchable
        text is already in `segments`. If object storage hiccups here the source still
        becomes usable, it just has no downloadable transcript.
        """
        key = self._transcript_key(asset.storage_key)
        if not key:
            return None

        body = self._render_transcript(title, segments, timestamps_available)
        try:
            self.file_storage.upload(key, body.encode("utf-8"), "text/markdown")
        except Exception:  # noqa: BLE001 - a missing transcript file must not fail the source
            return None
        return key

    @staticmethod
    def _transcript_key(storage_key: str) -> str | None:
        if not storage_key or "/" not in storage_key:
            return None
        return f"{storage_key.rsplit('/', 1)[0]}/{TRANSCRIPT_FILENAME}"

    @staticmethod
    def _render_transcript(title: str, segments: list[dict], timestamps_available: bool) -> str:
        lines = [f"# {title}", ""]
        if not timestamps_available:
            lines.append(
                "_This recording was transcribed without timings, so passages are numbered "
                "rather than timestamped._"
            )
            lines.append("")

        for segment in segments:
            locator = segment.get("locator") or {}
            if locator.get("type") == "timestamp":
                heading = _clock(int(locator.get("value") or 0))
            else:
                heading = str(locator.get("value") or "Part")
            lines.append(f"## {heading}")
            lines.append("")
            lines.append(segment["text"])
            lines.append("")

        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _title(filename: str) -> str:
        stem = filename.rsplit(".", 1)[0] if "." in filename else filename
        return sanitize_text_for_storage(stem or filename)


def _clock(total_seconds: int) -> str:
    hours, remainder = divmod(max(0, total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
