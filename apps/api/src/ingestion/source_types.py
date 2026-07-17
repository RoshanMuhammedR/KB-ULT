from __future__ import annotations

from pathlib import Path

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
