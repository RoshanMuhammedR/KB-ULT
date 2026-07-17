from __future__ import annotations

from typing import BinaryIO, Protocol


class IFileStorage(Protocol):
    def upload(self, key: str, file_data: bytes | BinaryIO, content_type: str) -> str:
        """Store file data and return the object key."""

    def download(self, key: str) -> bytes:
        """Read an object's bytes back.

        Used by the ingestion worker to re-fetch the source instead of carrying
        file bytes through the queue payload. Also what makes a failed extraction
        retryable without the client re-uploading the file.
        """

    def get_presigned_url(self, key: str, expires_in_seconds: int = 900) -> str:
        """Return a temporary signed URL for reading an object."""

    def delete(self, key: str) -> None:
        """Delete an object by key."""
