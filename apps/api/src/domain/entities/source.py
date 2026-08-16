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

    PDF = "pdf"             # acquire = object storage, parse = one document per page
    YOUTUBE = "youtube"     # acquire = transcript API, parse = timestamped documents
    MARKDOWN = "markdown"   # acquire = object storage, parse = heading-delimited sections
    PPTX = "pptx"           # acquire = object storage, parse = one document per slide
    AUDIO = "audio"         # acquire = object storage, parse = transcribed timestamped documents
    # WEBSITE = "website"   # planned: acquire = HTTP fetch, parse = HTML -> markdown


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source_type: str
    filename: str | None = None
    content_type: str | None = None
