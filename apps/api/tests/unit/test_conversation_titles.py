from unittest import TestCase

from src.application.chat.titles import MAX_TITLE_LENGTH, title_from_question


class TitleFromQuestionTest(TestCase):
    def test_short_question_becomes_the_title_verbatim(self) -> None:
        self.assertEqual(
            title_from_question("What did the Q2 filing say about margins?"),
            "What did the Q2 filing say about margins",
        )

    def test_collapses_whitespace(self) -> None:
        self.assertEqual(title_from_question("  What   about\n  margins? "), "What about margins")

    def test_truncates_at_a_word_boundary(self) -> None:
        question = (
            "What did the second quarter filing say about the effect of supply chain delays "
            "on operating margins across the European distribution network?"
        )

        title = title_from_question(question)

        self.assertTrue(title.endswith("…"))
        self.assertLessEqual(len(title), MAX_TITLE_LENGTH + 1)
        # Cut on whitespace, so the last word is never sliced in half.
        self.assertFalse(title[:-1].endswith(" "))
        self.assertTrue(question.startswith(title[:-1]))

    def test_blank_question_gets_a_fallback(self) -> None:
        self.assertEqual(title_from_question("   ?  "), "New conversation")

    def test_single_very_long_word_is_still_bounded(self) -> None:
        title = title_from_question("a" * 200)

        self.assertLessEqual(len(title), MAX_TITLE_LENGTH + 1)
