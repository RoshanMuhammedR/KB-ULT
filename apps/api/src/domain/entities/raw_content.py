from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RawContent:
    """Source-neutral payload produced by a handler's `acquire` step.

    Sits between acquisition (fetch the source) and parsing (normalize it into a
    `KnowledgeAsset`). It is deliberately untyped about *how* the bytes/text were
    obtained so the same parse step works regardless of origin:

      * PDF today: `data` is the file bytes downloaded from object storage.
      * Website later: `data` is the fetched HTML text.
      * YouTube later: `data` is the transcript payload.

    `mime` and `metadata` let a handler pass acquisition details (content type,
    fetched URL, HTTP status, ...) to its own parse step without widening the port.
    """

    data: bytes | str
    mime: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
