from __future__ import annotations

from collections.abc import AsyncIterator

from src.domain.entities import Embedding
from src.infrastructure.langchain_adapters.chat_model import OpenAICompatibleChatAdapter
from src.infrastructure.langchain_adapters.embeddings import OpenAICompatibleEmbeddingsAdapter


class AICreditsEmbeddingProvider:
    def __init__(
        self,
        adapter: OpenAICompatibleEmbeddingsAdapter,
        model: str,
        expected_dimensions: int,
    ) -> None:
        self.adapter = adapter
        self.model = model
        self.expected_dimensions = expected_dimensions

    async def embed_texts(self, texts: list[str]) -> list[Embedding]:
        vectors = await self.adapter.embed_texts(texts)
        return [self._to_embedding(vector) for vector in vectors]

    async def embed_query(self, text: str) -> list[float]:
        vector = await self.adapter.embed_query(text)
        self._validate(vector)
        return vector

    def _to_embedding(self, vector: list[float]) -> Embedding:
        self._validate(vector)
        return Embedding(vector=vector, model=self.model, dimensions=len(vector))

    def _validate(self, vector: list[float]) -> None:
        if len(vector) != self.expected_dimensions:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.expected_dimensions}, got {len(vector)}"
            )


class AICreditsLLMProvider:
    def __init__(self, adapter: OpenAICompatibleChatAdapter) -> None:
        self.adapter = adapter

    async def generate(self, messages: list[dict[str, str]]) -> str:
        return await self.adapter.generate(messages)

    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        # Not `async def`: an async generator function already returns its iterator, so
        # forwarding it directly keeps `async for provider.stream(...)` working without an
        # extra await at every call site.
        return self.adapter.stream(messages)
