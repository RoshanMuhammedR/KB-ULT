from unittest import TestCase

from src.core.text import sanitize_json_for_storage, sanitize_text_for_storage


class TextSanitizerTest(TestCase):
    def test_removes_nul_bytes_from_text(self) -> None:
        self.assertEqual(sanitize_text_for_storage("a\x00b"), "ab")

    def test_removes_nul_bytes_recursively_from_json_values(self) -> None:
        self.assertEqual(
            sanitize_json_for_storage({"pa\x00ges": [{"text": "he\x00llo"}]}),
            {"pages": [{"text": "hello"}]},
        )
