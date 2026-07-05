from __future__ import annotations

from pathlib import Path

from src.domain.interfaces import IParser


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, IParser] = {}

    def register(self, extension: str, parser: IParser) -> None:
        normalized = self._normalize(extension)
        self._parsers[normalized] = parser

    def get(self, filename_or_extension: str) -> IParser:
        extension = self._normalize(filename_or_extension)
        try:
            return self._parsers[extension]
        except KeyError as exc:
            supported = ", ".join(sorted(self._parsers))
            raise ValueError(f"Unsupported source type {extension}. Supported: {supported}") from exc

    def supports(self, filename_or_extension: str) -> bool:
        return self._normalize(filename_or_extension) in self._parsers

    def _normalize(self, filename_or_extension: str) -> str:
        if filename_or_extension.startswith("."):
            return filename_or_extension.lower()
        return Path(filename_or_extension).suffix.lower()
