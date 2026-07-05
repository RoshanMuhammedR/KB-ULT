from __future__ import annotations

from typing import Protocol


class ILLMProvider(Protocol):
    def generate(self, messages: list[dict[str, str]]) -> str:
        """Generate a final answer from chat messages."""
