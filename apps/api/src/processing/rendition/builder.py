"""Build and store a source's page renditions.

One place owns the object-key scheme, because that scheme is what guarantees coordinates and
images can never disagree:

    {tenant_id}/{asset_id}/render/v{render_version}/p{page:04d}.{ext}

`render_version` is bumped whenever renditions are rebuilt, and the chunk coordinates that go
with them are rewritten in the same reprocess by `chunk_repo.replace_for_asset`. A viewer
always reads the current version off the asset row, so v2 coordinates can never be paired with
v1 images. Old versions are simply orphaned and swept lazily.

Failure here is never fatal. A source whose rendition cannot be built keeps its extracted text
and is downgraded to the TEXT shape, which is a working view — losing page images is a smaller
loss than losing the source.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

import structlog

from src.core.tenant_context import current_tenant_id
from src.domain.entities import CanonicalShape, KnowledgeAsset
from src.domain.interfaces import IFileStorage

logger = structlog.get_logger(__name__)

# Renditions are immutable once written — the version in the key changes instead — so they can
# be cached essentially forever by any proxy that sees them.
_RENDITION_CACHE_CONTROL = "public, max-age=31536000, immutable"


class IPageRenderer(Protocol):
    """Turns source bytes into one image per page."""

    ext: str
    mime: str

    def render(self, file_data: bytes) -> Any:
        """Yield `(page_number, image_bytes, width_pt, height_pt)`."""
        ...


def rendition_key(tenant_id: UUID | str, asset_id: UUID, version: int, page: int, ext: str) -> str:
    return f"{tenant_id}/{asset_id}/render/v{version}/p{page:04d}.{ext}"


class RenditionBuilder:
    def __init__(self, file_storage: IFileStorage) -> None:
        self.file_storage = file_storage
        self._renderers: dict[str, IPageRenderer] = {}

    def register(self, source_type: str, renderer: IPageRenderer) -> None:
        """Adding a format's page rendering is this one call — no client change."""
        self._renderers[source_type] = renderer

    def supports(self, source_type: str) -> bool:
        return source_type in self._renderers

    def build(self, asset: KnowledgeAsset, file_data: bytes) -> KnowledgeAsset:
        """Render every page, upload it, and stamp the manifest onto the asset.

        Mutates and returns `asset`; the caller persists it. On any failure the asset is
        downgraded to TEXT with no manifest, so the viewer falls back rather than pointing at
        images that were never written.
        """
        renderer = self._renderers.get(asset.source_type)
        if renderer is None or not file_data:
            return asset

        version = asset.render_version + 1
        tenant_id = current_tenant_id()
        pages: list[dict[str, Any]] = []

        try:
            for page_number, image_bytes, width_pt, height_pt in renderer.render(file_data):
                key = rendition_key(tenant_id, asset.id, version, page_number, renderer.ext)
                self.file_storage.upload(
                    key=key,
                    file_data=image_bytes,
                    content_type=renderer.mime,
                    cache_control=_RENDITION_CACHE_CONTROL,
                )
                pages.append(
                    {
                        "n": page_number,
                        "w": round(width_pt, 2),
                        "h": round(height_pt, 2),
                        "ext": renderer.ext,
                    }
                )
        except Exception as exc:  # noqa: BLE001 - a rendition is an enhancement, never a gate
            logger.warning(
                "rendition_failed",
                knowledge_asset_id=str(asset.id),
                source_type=asset.source_type,
                error=str(exc),
            )
            return self._downgrade(asset)

        if not pages:
            return self._downgrade(asset)

        asset.render_version = version
        asset.page_manifest = {"pages": pages}
        asset.canonical_shape = str(CanonicalShape.PAGED)
        logger.info(
            "rendition_built",
            knowledge_asset_id=str(asset.id),
            render_version=version,
            page_count=len(pages),
            ext=renderer.ext,
        )
        return asset

    @staticmethod
    def _downgrade(asset: KnowledgeAsset) -> KnowledgeAsset:
        """Fall back to the text view rather than claiming a shape we cannot render."""
        asset.page_manifest = None
        asset.canonical_shape = str(CanonicalShape.TEXT)
        return asset
