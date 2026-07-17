from __future__ import annotations

from src.domain.entities import SourceType
from src.domain.interfaces import ISourceHandler


class SourceHandlerRegistry:
    """Maps a `SourceType` to the handler that acquires + parses it.

    Replaces the old extension-keyed parser registry: dispatch is now by source type,
    not file extension, so non-file sources (a URL has no extension) fit the same
    lookup. The composition root registers one handler per supported type; the
    ingestion service looks a handler up by `asset.source_type`.
    """

    def __init__(self) -> None:
        self._handlers: dict[SourceType, ISourceHandler] = {}

    def register(self, source_type: SourceType, handler: ISourceHandler) -> None:
        self._handlers[source_type] = handler

    def get(self, source_type: SourceType) -> ISourceHandler:
        try:
            return self._handlers[source_type]
        except KeyError as exc:
            supported = ", ".join(sorted(st.value for st in self._handlers))
            raise ValueError(
                f"Unsupported source type '{source_type}'. Supported: {supported}"
            ) from exc

    def supports(self, source_type: SourceType) -> bool:
        return source_type in self._handlers
