from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SourceType(StrEnum):
    """The kind of source an asset was ingested from.

    Dispatch key for the source-handler registry (which handler acquires + parses a
    given asset). It is a `StrEnum`, so its members compare/serialize as plain strings
    and can be stored straight into the `knowledge_assets.source_type` String column
    with no migration.

    Only PDF is implemented today. WEBSITE/YOUTUBE are reserved so the shape of the
    system (registry, resolver, handlers) is already source-agnostic — adding them
    later is a new handler plus a resolver branch, nothing structural.
    """

    PDF = "pdf"
    # WEBSITE = "website"   # planned: acquire = HTTP fetch, parse = HTML -> markdown
    # YOUTUBE = "youtube"   # planned: acquire = transcript API, parse = timestamped text


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source_type: str
    filename: str | None = None
    content_type: str | None = None
