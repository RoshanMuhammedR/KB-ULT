from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SourceType(StrEnum):
    """The kind of source an asset was ingested from.

    Dispatch key for the source-handler registry (which handler acquires + parses a
    given asset). It is a `StrEnum`, so its members compare/serialize as plain strings
    and can be stored straight into the `knowledge_assets.source_type` String column
    with no migration.

    All members below are implemented. WEBSITE is reserved so the shape of the system
    (registry, resolvers, handlers) stays source-agnostic — adding it is a new handler
    plus a resolver branch, nothing structural.
    """

    PDF = "pdf"
    YOUTUBE = "youtube"    # acquire = transcript API, parse = timestamped segments
    MARKDOWN = "markdown"  # acquire = object storage, parse = heading-delimited sections
    PPTX = "pptx"          # acquire = object storage, parse = one segment per slide
    AUDIO = "audio"        # acquire = object storage, parse = transcribed timestamped segments
    # WEBSITE = "website"   # planned: acquire = HTTP fetch, parse = HTML -> markdown


class CanonicalShape(StrEnum):
    """How a source is *displayed*, as opposed to what file it came from.

    The viewer switches on this and never learns about formats, which is what keeps adding a
    format a server-side change. There are exactly three, and there is deliberately no fourth:

      * PAGED — has discrete pages with 2D geometry (PDF; PPTX once slides render).
      * TIMELINE — has a playhead and 1D time offsets (audio, YouTube).
      * TEXT — has neither. Markdown lives here permanently; anything whose rendition failed
        degrades to here rather than failing ingestion, so this doubles as the honest
        fallback surface.
    """

    PAGED = "paged"
    TIMELINE = "timeline"
    TEXT = "text"


# Kept beside SourceType so a new source type that forgets its shape is obvious here rather
# than silently defaulting somewhere downstream.
_SHAPE_BY_SOURCE_TYPE: dict[SourceType, CanonicalShape] = {
    SourceType.PDF: CanonicalShape.PAGED,
    SourceType.PPTX: CanonicalShape.PAGED,
    SourceType.AUDIO: CanonicalShape.TIMELINE,
    SourceType.YOUTUBE: CanonicalShape.TIMELINE,
    SourceType.MARKDOWN: CanonicalShape.TEXT,
}


def shape_for_source_type(source_type: str) -> CanonicalShape:
    """Resolve a source type's display shape, defaulting to TEXT.

    TEXT is the safe default: it renders the extracted text, which every source has by
    definition, so an unrecognised type degrades to something usable instead of a blank view.
    """
    try:
        return _SHAPE_BY_SOURCE_TYPE.get(SourceType(source_type), CanonicalShape.TEXT)
    except ValueError:
        return CanonicalShape.TEXT


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source_type: str
    filename: str | None = None
    content_type: str | None = None
