from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    values: tuple[float, ...]

    @property
    def dimensions(self) -> int:
        return len(self.values)
