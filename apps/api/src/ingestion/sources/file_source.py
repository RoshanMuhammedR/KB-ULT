from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True, slots=True)
class FileSource:
    asset_id: UUID
    file_data: bytes
    filename: str
    storage_key: str
    knowledge_base_id: UUID
    lineage_id: UUID
    version: int
    content_type: str | None = None

    @property
    def extension(self) -> str:
        return Path(self.filename).suffix.lower()
