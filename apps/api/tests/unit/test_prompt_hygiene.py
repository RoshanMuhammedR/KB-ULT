"""A quiet corruption: a stale citation number.

It never raises. It produces an answer that looks fine and is not.
"""

import unittest

from src.application.chat.agentic.prompts import build_messages


class StaleCitationTest(unittest.TestCase):
    """A previous answer's `[1]` refers to a passage this turn never retrieved.

    Injected verbatim into the history, it is an example in the model's own context of how to
    cite — pointing at a number that now means something else. That is worse than an invented
    citation: `invalid_ordinals` catches a number with no passage behind it, and nothing
    catches a valid number in front of the wrong one.
    """

    def _history(self):
        return [
            {"role": "user", "content": "What is the notice period?"},
            {"role": "assistant", "content": "It is thirty days [1]. Billing is monthly [2, 3]."},
        ]

    def test_markers_are_stripped_from_previous_answers(self) -> None:
        messages = build_messages("And for contractors?", ["[1] new"], history=self._history())

        prior = next(m for m in messages if m["role"] == "assistant")

        self.assertNotIn("[1]", prior["content"])
        self.assertNotIn("[2, 3]", prior["content"])

    def test_the_prose_survives_because_that_is_what_history_is_for(self) -> None:
        """A follow-up is resolved against what was said. "thirty days" does that work; the
        bracket was only provenance for a context that has since been replaced."""
        messages = build_messages("And for contractors?", ["[1] new"], history=self._history())

        prior = next(m for m in messages if m["role"] == "assistant")

        self.assertEqual(prior["content"], "It is thirty days. Billing is monthly.")

    def test_the_users_own_words_are_never_touched(self) -> None:
        messages = build_messages("And for contractors?", ["[1] new"], history=self._history())

        asked = next(m for m in messages if m["role"] == "user" and "notice" in m["content"])

        self.assertEqual(asked["content"], "What is the notice period?")

    def test_this_turns_context_is_still_numbered(self) -> None:
        messages = build_messages("And for contractors?", ["[1] new"], history=self._history())

        self.assertIn("[1] new", messages[-1]["content"])
