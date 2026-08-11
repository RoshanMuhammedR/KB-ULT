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
        # Deliberately NOT built here. Constructing a docling DocumentConverter imports torch
        # and loads the layout (+ optionally TableFormer) weights — hundreds of MB of RSS and
        # a multi-second stall. The HTTP layer builds this adapter on the upload endpoints
        # just to validate the source type and never parses anything, so paying that cost in
        # __init__ put torch in the api container for no reason. Built on first `load()`
        # instead; see `converter`.
        self._converter = converter
        self.document_stream_factory = document_stream_factory or self._build_document_stream

    @property
    def converter(self) -> Any:
        if self._converter is None:
            self._converter = self._build_converter()
        return self._converter

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
        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
        from docling.document_converter import DocumentConverter, PdfFormatOption

        from src.core.config import get_settings

        settings = get_settings()

        pipeline_options = PdfPipelineOptions()
        # OCR stays off for the MVP to keep local setup and upload latency lighter.
        pipeline_options.do_ocr = False
        # Table structure is a whole second torch model (TableFormer) run over every detected
        # table, and docling's default mode for it is ACCURATE — its slowest. Turning OCR off
        # while leaving this at its defaults was the main reason a 20-page PDF took minutes on
        # 2 vCPU. See `docling_do_table_structure` in core/config.py for the trade-off.
        pipeline_options.do_table_structure = settings.docling_do_table_structure
        pipeline_options.table_structure_options.mode = TableFormerMode.FAST
        # Docling enforces no timeout by default; without one a single pathological PDF holds
        # the (concurrency-1) worker forever. Partial results come back as PARTIAL_SUCCESS.
        pipeline_options.document_timeout = settings.docling_timeout_seconds
        pipeline_options.accelerator_options = AcceleratorOptions(
            # Docling defaults to 4; this box has 2 vCPU. docling_ibm_models applies this via
            # torch.set_num_threads(), so it is the real knob, not just a hint.
            num_threads=settings.docling_num_threads,
            # Explicit "cpu" skips decide_device()'s CUDA/MPS/XPU probe. There is no GPU here
            # and the image ships CPU-only torch, so the probe can only ever answer "cpu".
            device="cpu",
        )
        return DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)},
        )

    def _build_document_stream(self, **kwargs: Any) -> Any:
        from docling.datamodel.base_models import DocumentStream

        return DocumentStream(**kwargs)
