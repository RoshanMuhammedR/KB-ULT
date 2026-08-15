from __future__ import annotations

from typing import BinaryIO, Protocol


class IFileStorage(Protocol):
    def upload(
        self,
        key: str,
        file_data: bytes | BinaryIO,
        content_type: str,
        cache_control: str | None = None,
    ) -> str:
        """Store file data and return the object key.

        `cache_control` is set on the object itself, so any proxy in front of storage honours
        it. Used for renditions, which are immutable — a new render writes a new versioned key
        rather than overwriting — and can therefore be cached indefinitely.
        """

    def download(self, key: str) -> bytes:
        """Read an object's bytes back.

        Used by the ingestion worker to re-fetch the source instead of carrying
        file bytes through the queue payload. Also what makes a failed extraction
        retryable without the client re-uploading the file.
        """

    def get_presigned_url(self, key: str, expires_in_seconds: int = 60) -> str:
        """Return a temporary signed URL for reading an object.

        Short-lived by default: the URL carries its own authorization, so anyone holding it
        can read the object regardless of tenancy until it expires. 60s is enough to follow
        a redirect and start a download, and short enough that a leaked URL is worthless.
        """

    def delete(self, key: str) -> None:
        """Delete an object by key."""
