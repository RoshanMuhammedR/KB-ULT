from __future__ import annotations

from io import BytesIO
from typing import Any, Callable

from src.core.text import sanitize_text_for_storage


class DoclingPDFAdapter:
    def __init__(
        self,
        converter: Any | None = None,
        document_stream_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.converter = converter or self._build_converter()
        self.document_stream_factory = document_stream_factory or self._build_document_stream

    def load(self, file_data: bytes, filename: str) -> dict[str, Any]:
        # Feed Docling an in-memory stream so uploads do not need permanent local files.
        source = self.document_stream_factory(name=filename, stream=BytesIO(file_data))
        result = self.converter.convert(source)
        document = result.document
        markdown = sanitize_text_for_storage(document.export_to_markdown()).strip()
        pages = self._extract_pages(document, markdown)

        return {
            "markdown": markdown,
            "pages": pages,
            "title": self._extract_title(document),
            # Keep stored metadata small; the raw Docling document can be large.
            "metadata": {
                "status": self._stringify(getattr(result, "status", None)),
                "errors": len(getattr(result, "errors", []) or []),
                "page_count": len(pages),
            },
        }

    def _extract_pages(self, document: Any, markdown: str) -> list[dict[str, Any]]:
        page_numbers = self._page_numbers(document)
        pages: list[dict[str, Any]] = []
        for page_number in page_numbers:
            try:
                page_markdown = document.export_to_markdown(page_no=page_number)
            except TypeError:
                return self._fallback_pages(markdown)
            page_markdown = sanitize_text_for_storage(page_markdown).strip()
            if page_markdown:
                pages.append({"page_number": page_number, "text": page_markdown})
        return pages or self._fallback_pages(markdown)

    def _page_numbers(self, document: Any) -> list[int]:
        pages = getattr(document, "pages", None)
        if isinstance(pages, dict):
            return sorted(int(page_number) for page_number in pages)
        if isinstance(pages, list):
            return list(range(1, len(pages) + 1))
        return []

    def _fallback_pages(self, markdown: str) -> list[dict[str, Any]]:
        return [{"page_number": None, "text": markdown}] if markdown else []

    def _extract_title(self, document: Any) -> str | None:
        for attr in ("title", "name"):
            value = getattr(document, attr, None)
            if value:
                return sanitize_text_for_storage(str(value))
        return None

    def _stringify(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(getattr(value, "value", value))

    def _build_converter(self) -> Any:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        pipeline_options = PdfPipelineOptions()
        # OCR stays off for the MVP to keep local setup and upload latency lighter.
        pipeline_options.do_ocr = False
        return DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)},
        )

    def _build_document_stream(self, **kwargs: Any) -> Any:
        from docling.datamodel.base_models import DocumentStream

        return DocumentStream(**kwargs)
