from unittest import TestCase

import pymupdf

from src.infrastructure.document_parsing import PyMuPDF4LLMAdapter


class PyMuPDF4LLMAdapterTest(TestCase):
    def _sample_pdf_bytes(self, texts: list[str], title: str | None = None) -> bytes:
        document = pymupdf.open()
        for text in texts:
            page = document.new_page()
            page.insert_text((72, 72), text)
        if title is not None:
            document.set_metadata({"title": title})
        data = document.tobytes()
        document.close()
        return data

    def test_converts_multi_page_pdf_to_markdown_with_page_locators(self) -> None:
        pdf_bytes = self._sample_pdf_bytes(
            ["First page body", "Second page body"], title="Sample Title"
        )
        adapter = PyMuPDF4LLMAdapter()

        parsed = adapter.load(pdf_bytes, "sample.pdf")

        self.assertEqual(parsed["title"], "Sample Title")
        self.assertEqual(len(parsed["pages"]), 2)
        self.assertEqual(parsed["pages"][0]["page_number"], 1)
        self.assertIn("First page body", parsed["pages"][0]["text"])
        self.assertEqual(parsed["pages"][1]["page_number"], 2)
        self.assertIn("Second page body", parsed["pages"][1]["text"])
        self.assertIn("First page body", parsed["markdown"])
        self.assertIn("Second page body", parsed["markdown"])
        self.assertEqual(parsed["metadata"], {"status": "success", "errors": 0, "page_count": 2})

    def test_pdf_without_a_title_falls_back_to_none(self) -> None:
        pdf_bytes = self._sample_pdf_bytes(["Body text"])
        adapter = PyMuPDF4LLMAdapter()

        parsed = adapter.load(pdf_bytes, "untitled.pdf")

        self.assertIsNone(parsed["title"])
