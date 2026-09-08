"""Two quiet corruptions: a stale citation number, and a wrong-width cached vector.

Neither raises. Both produce an answer that looks fine and is not.
"""

import json
import unittest
from unittest import IsolatedAsyncioTestCase

from src.application.chat.agentic.prompts import build_messages
from src.infrastructure.cache.query_cache import EmbeddingCache


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


class _Cache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl_seconds=None):
        self.store[key] = value


class _Inner:
    def __init__(self, width: int = 1536) -> None:
        self.calls = 0
        self.width = width

    async def embed_query(self, text):
        self.calls += 1
        return [0.1] * self.width


class EmbeddingCacheTest(IsolatedAsyncioTestCase):
    """A cached vector of the wrong width reaches pgvector as a runtime failure three layers
    from its cause."""

    async def test_dimensions_are_part_of_the_key(self) -> None:
        """A gateway can serve a different width under the same model id, and
        `embedding_dimensions` is a setting someone can change."""
        cache = _Cache()
        wide = EmbeddingCache(_Inner(1536), cache, model="m", ttl_seconds=60, dimensions=1536)
        narrow = EmbeddingCache(_Inner(768), cache, model="m", ttl_seconds=60, dimensions=768)

        await wide.embed_query("hello")
        await narrow.embed_query("hello")

        self.assertEqual(len(cache.store), 2, "same text and model must not share a key")

    async def test_a_hit_is_reused(self) -> None:
        inner = _Inner()
        embedder = EmbeddingCache(inner, _Cache(), model="m", ttl_seconds=60, dimensions=1536)

        await embedder.embed_query("hello")
        await embedder.embed_query("hello")

        self.assertEqual(inner.calls, 1)

    async def test_a_wrong_width_entry_is_refused_and_re_embedded(self) -> None:
        cache = _Cache()
        inner = _Inner(1536)
        embedder = EmbeddingCache(inner, cache, model="m", ttl_seconds=60, dimensions=1536)
        await embedder.embed_query("hello")
        cache.store[next(iter(cache.store))] = json.dumps([0.1] * 768)

        vector = await embedder.embed_query("hello")

        self.assertEqual(len(vector), 1536)
        self.assertEqual(inner.calls, 2)

    async def test_a_non_vector_entry_is_refused(self) -> None:
        """Redis has no auth in the default config, so whatever can write a key would
        otherwise choose the query vector for every tenant asking that question."""
        cache = _Cache()
        inner = _Inner()
        embedder = EmbeddingCache(inner, cache, model="m", ttl_seconds=60, dimensions=1536)
        await embedder.embed_query("hello")
        cache.store[next(iter(cache.store))] = json.dumps({"not": "a vector"})

        vector = await embedder.embed_query("hello")

        self.assertEqual(len(vector), 1536)
        self.assertEqual(inner.calls, 2)


if __name__ == "__main__":
    unittest.main()
