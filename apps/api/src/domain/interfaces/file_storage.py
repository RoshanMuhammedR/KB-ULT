from __future__ import annotations

from typing import BinaryIO, Protocol


class IFileStorage(Protocol):
    def upload(self, key: str, file_data: bytes | BinaryIO, content_type: str) -> str:
        """Store file data and return the object key."""

    def get_presigned_url(self, key: str, expires_in_seconds: int = 900) -> str:
        """Return a temporary signed URL for reading an object."""

    def delete(self, key: str) -> None:
        """Delete an object by key."""
