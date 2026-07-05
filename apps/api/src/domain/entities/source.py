from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source_type: str
    filename: str | None = None
    content_type: str | None = None
