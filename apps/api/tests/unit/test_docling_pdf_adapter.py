from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from src.infrastructure.document_parsing import DoclingPDFAdapter


class DoclingPDFAdapterTest(TestCase):
    def test_converts_pdf_bytes_to_markdown_without_permanent_file_path(self) -> None:
        document = Mock()
        document.pages = {1: object(), 2: object()}
        document.title = "Doc\x00 Title"
        document.export_to_markdown.side_effect = lambda **kwargs: {
            (): "# Doc\x00 Title\n\nBody",
            (("page_no", 1),): "# Doc\x00 Title",
            (("page_no", 2),): "Body",
        }[tuple(kwargs.items())]
        converter = Mock()
        converter.convert.return_value = SimpleNamespace(
            document=document,
            status=SimpleNamespace(value="success"),
            errors=[],
        )

        stream_kwargs = []
        stream_objects = []

        def stream_factory(**kwargs):
            stream_kwargs.append(kwargs)
            stream = SimpleNamespace(**kwargs)
            stream_objects.append(stream)
            return stream

        adapter = DoclingPDFAdapter(converter=converter, document_stream_factory=stream_factory)

        parsed = adapter.load(b"%PDF", "sample.pdf")

        self.assertEqual(parsed["markdown"], "# Doc Title\n\nBody")
        self.assertEqual(parsed["title"], "Doc Title")
        self.assertEqual(
            parsed["pages"],
            [
                {"page_number": 1, "text": "# Doc Title"},
                {"page_number": 2, "text": "Body"},
            ],
        )
        self.assertEqual(parsed["metadata"], {"status": "success", "errors": 0, "page_count": 2})
        self.assertEqual(stream_kwargs[0]["name"], "sample.pdf")
        self.assertEqual(stream_kwargs[0]["stream"].getvalue(), b"%PDF")
        converter.convert.assert_called_once_with(stream_objects[0])

    def test_falls_back_to_single_markdown_page_when_page_export_is_unavailable(self) -> None:
        document = Mock()
        document.pages = {}
        document.title = None
        document.export_to_markdown.return_value = "# Only markdown"
        converter = Mock()
        converter.convert.return_value = SimpleNamespace(document=document, status=None, errors=None)
        adapter = DoclingPDFAdapter(
            converter=converter,
            document_stream_factory=lambda **kwargs: SimpleNamespace(**kwargs),
        )

        parsed = adapter.load(b"%PDF", "sample.pdf")

        self.assertEqual(parsed["pages"], [{"page_number": None, "text": "# Only markdown"}])
        self.assertEqual(parsed["metadata"]["page_count"], 1)
