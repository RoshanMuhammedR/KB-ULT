"""Rasterize PDF pages to JPEG, in the worker, once per ingest.

Rendering never happens in the API container: the API only signs URLs, so PyMuPDF's memory
profile stays out of the 512m web process entirely. It also never happens per view — the
images are written to object storage during ingestion, while the file is already open.
"""

from __future__ import annotations

from typing import Any, Iterator

# ~130 DPI renders a US-Letter page at roughly 1100x1400, which is sharp enough to read on a
# high-density display at fit-to-width without the file size of a 200 DPI render.
RENDER_DPI = 130

# Past this, rendering a whole document costs more than the feature is worth and the viewer
# degrades to the text view instead. Chosen to be far above any realistic cited document.
MAX_RENDERED_PAGES = 500

# JPEG rather than WebP: PyMuPDF's WebP support depends on how the wheel was built and Pillow
# is not a direct dependency, so JPEG is the format that is certain to work. Revisit as an
# optimization once the size delta has actually been measured.
PAGE_IMAGE_EXT = "jpg"
PAGE_IMAGE_MIME = "image/jpeg"


class PdfPageRenderer:
    """Yields `(page_number, image_bytes, width_pt, height_pt)` for each page."""

    shape = "paged"
    ext = PAGE_IMAGE_EXT
    mime = PAGE_IMAGE_MIME

    def render(self, file_data: bytes) -> Iterator[tuple[int, bytes, float, float]]:
        import pymupdf

        document = pymupdf.open(stream=file_data, filetype="pdf")
        try:
            for page_index, page in enumerate(document, start=1):
                if page_index > MAX_RENDERED_PAGES:
                    break
                rect = page.rect
                pixmap = page.get_pixmap(dpi=RENDER_DPI)
                try:
                    yield (
                        page_index,
                        pixmap.tobytes("jpeg"),
                        float(rect.width),
                        float(rect.height),
                    )
                finally:
                    # Pixmaps hold their full uncompressed bitmap; dropping each one before
                    # the next keeps peak memory at roughly one page rather than the document.
                    del pixmap
        finally:
            document.close()

    @staticmethod
    def page_count(file_data: bytes) -> int:
        import pymupdf

        document = pymupdf.open(stream=file_data, filetype="pdf")
        try:
            return int(document.page_count)
        finally:
            document.close()


def is_renderable(parsed_metadata: dict[str, Any] | None) -> bool:
    """Whether rendering this document is worth attempting at all."""
    if not parsed_metadata:
        return True
    page_count = parsed_metadata.get("page_count")
    return not (isinstance(page_count, int) and page_count > MAX_RENDERED_PAGES)
