"""Hosted speech-to-text through the AICredits gateway.

Deliberately an HTTP client and nothing more: no local model, no torch, no weights in the
image. Transcription runs worker-side, so the timeout is generous rather than request-shaped.
"""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger(__name__)

# A long audio file legitimately takes minutes. This is a worker task, not a request.
_TIMEOUT_SECONDS = 600.0

# Status codes that mean "this gateway doesn't expose /audio/transcriptions", as opposed to
# "the request was bad". Only these justify the chat-completions fallback.
_ROUTE_MISSING_STATUSES = frozenset({404, 405, 422})


@dataclass(slots=True)
class Transcript:
    text: str
    #: `[{text, start}]` — empty when the provider returned no timings.
    segments: list[dict] = field(default_factory=list)
    duration: float | None = None

    @property
    def has_timestamps(self) -> bool:
        return bool(self.segments)


class VoxtralTranscriptionProvider:
    """Transcribes audio via the OpenAI-compatible `/audio/transcriptions` route.

    Falls back once to `/chat/completions` with an inline base64 audio part when the
    gateway doesn't expose the transcription route. The fallback returns plain text with no
    timings, which the audio handler turns into honest `section` locators rather than
    invented timestamps.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = _TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def transcribe(self, data: bytes, filename: str) -> Transcript:
        if not self.api_key:
            raise ValueError("Audio transcription is not configured on this server")

        try:
            return self._transcribe_route(data, filename)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _ROUTE_MISSING_STATUSES:
                raise ValueError(self._error_message(exc)) from exc
            logger.info(
                "transcription_route_unavailable",
                status=exc.response.status_code,
                model=self.model,
            )
        except httpx.HTTPError as exc:
            raise ValueError(f"Could not reach the transcription service: {exc}") from exc

        try:
            return self._transcribe_chat(data, filename)
        except httpx.HTTPStatusError as exc:
            raise ValueError(self._error_message(exc)) from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"Could not reach the transcription service: {exc}") from exc

    # --- Transports ---------------------------------------------------------------

    def _transcribe_route(self, data: bytes, filename: str) -> Transcript:
        response = httpx.post(
            f"{self.base_url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            files={"file": (filename, data, self._content_type(filename))},
            data={
                "model": self.model,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "segment",
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return self._parse_verbose_json(response.json())

    def _transcribe_chat(self, data: bytes, filename: str) -> Transcript:
        # The audio-in-chat shape: an `input_audio` content part alongside a text prompt.
        encoded = base64.b64encode(data).decode("ascii")
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Transcribe this audio verbatim. Return only the transcript "
                                    "text, with no commentary, headings, or timestamps."
                                ),
                            },
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": encoded,
                                    "format": self._audio_format(filename),
                                },
                            },
                        ],
                    }
                ],
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()

        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("The transcription service returned an unexpected response") from exc

        if isinstance(text, list):
            # Some gateways return the content as a list of parts.
            text = "".join(part.get("text", "") for part in text if isinstance(part, dict))

        text = (text or "").strip()
        if not text:
            raise ValueError("No speech could be found in this audio file")
        return Transcript(text=text, segments=[], duration=None)

    # --- Parsing ------------------------------------------------------------------

    def _parse_verbose_json(self, payload: dict) -> Transcript:
        text = (payload.get("text") or "").strip()
        raw_segments = payload.get("segments") or []

        segments: list[dict] = []
        for segment in raw_segments:
            if not isinstance(segment, dict):
                continue
            segment_text = (segment.get("text") or "").strip()
            if not segment_text:
                continue
            start = segment.get("start")
            segments.append({"text": segment_text, "start": float(start or 0)})

        if not text and segments:
            text = " ".join(segment["text"] for segment in segments)
        if not text:
            raise ValueError("No speech could be found in this audio file")

        duration = payload.get("duration")
        return Transcript(
            text=text,
            segments=segments,
            duration=float(duration) if duration is not None else None,
        )

    # --- Helpers ------------------------------------------------------------------

    @staticmethod
    def _content_type(filename: str) -> str:
        return mimetypes.guess_type(filename)[0] or "application/octet-stream"

    @staticmethod
    def _audio_format(filename: str) -> str:
        return (Path(filename).suffix.lstrip(".") or "mp3").lower()

    @staticmethod
    def _error_message(exc: httpx.HTTPStatusError) -> str:
        status = exc.response.status_code
        if status == 413:
            return "This audio file is too large for the transcription service"
        if status == 429:
            return "The transcription service is rate limiting right now — retry in a minute"
        return f"The transcription service rejected this file (error {status})"
