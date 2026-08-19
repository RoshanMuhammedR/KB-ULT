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

    def get_presigned_url(self, key: str, expires_in_seconds: int = 60) -> str:
        """Return a temporary signed URL for reading an object.

        Short-lived by default: the URL carries its own authorization, so anyone holding it
        can read the object regardless of tenancy until it expires. 60s is enough to follow
        a redirect and start a download, and short enough that a leaked URL is worthless.
        """

    def get_presigned_put_url(self, key: str, content_type: str, expires_in_seconds: int = 900) -> str:
        """Return a temporary signed URL the client can PUT an object to directly.

        The counterpart of `get_presigned_url`, and the reason it exists: with one of these
        the browser sends the file straight to object storage, so the bytes never pass
        through — or sit in the memory of — the API process at all.

        `content_type` is part of what gets signed, so the client must send the same value
        it asked for. That is deliberate: it stops a URL issued for a PDF being reused to
        store something else.
        """

    def object_size(self, key: str) -> int | None:
        """Size in bytes of the object at this key, or None if there isn't one.

        Needed when the upload happened out-of-band: before recording an asset that claims
        an object exists, check that it does — and how big it is, since the size limits that
        a multipart upload hits in the request cannot be applied to bytes that never came
        through here.
        """

    def delete(self, key: str) -> None:
        """Delete an object by key."""
