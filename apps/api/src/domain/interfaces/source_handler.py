from __future__ import annotations

from typing import Protocol

from src.domain.entities import KnowledgeAsset
from src.domain.entities.raw_content import RawContent


class ISourceHandler(Protocol):
    """Everything source-specific for one `SourceType`, behind one port.

    A handler owns both I/O steps for its kind of source, so adding a new source
    (website, YouTube) means implementing this once and registering it — the
    application service, chunker, embedder, and chat stay untouched.

    Boundary rule: this is a domain port, so implementations live in `ingestion/`
    and `infrastructure/`; nothing here imports FastAPI/SQLAlchemy/Procrastinate.
    """

    def acquire(self, asset: KnowledgeAsset) -> RawContent:
        """Fetch the raw source content for an asset.

        For PDF this downloads the uploaded bytes from object storage; for a URL
        source it would fetch over HTTP. Kept separate from `parse` so acquisition
        can be skipped on a retry that already got past extraction.
        """

    def parse(self, asset: KnowledgeAsset, raw: RawContent) -> KnowledgeAsset:
        """Normalize raw content into an extracted `KnowledgeAsset`.

        Populates `text_content` and `documents`: one LangChain `Document` per natural
        unit of the source (a page, a slide, a heading section, a transcript window), each
        carrying a typed `metadata["locator"]` — e.g. `{"type": "page", "value": 3}`.

        Deciding *where the citable boundaries are* is the handler's job, because only it
        knows what they mean for its format. Deciding *how big each piece may be* is the
        chunker's, and is identical for every source — which is what leaves downstream
        chunking and embedding source-agnostic.
        """
