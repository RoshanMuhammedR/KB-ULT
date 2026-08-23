from __future__ import annotations

import asyncio
from typing import BinaryIO

import boto3

from src.core.config import Settings
from src.core.exceptions import FileStorageError
from src.domain.interfaces import IFileStorage


class FilebaseAdapter(IFileStorage):
    def __init__(self, settings: Settings) -> None:
        self.bucket_name = settings.filebase_bucket_name
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.filebase_endpoint,
            region_name="us-east-1",
            aws_access_key_id=settings.filebase_access_key,
            aws_secret_access_key=settings.filebase_secret_key,
        )

    async def upload(self, key: str, file_data: bytes | BinaryIO, content_type: str) -> str:
        # boto3 is synchronous: every call here goes to a worker thread so the event loop
        # keeps serving other requests while the object is in flight.
        try:
            await asyncio.to_thread(
                self.client.put_object,
                Bucket=self.bucket_name,
                Key=key,
                Body=file_data,
                ContentType=content_type,
            )
            return key
        except Exception as exc:
            raise FileStorageError(f"Failed to upload object: {key}") from exc

    async def download(self, key: str) -> bytes:
        # Read the whole object into memory. Used by the ingestion worker so the
        # queue payload can stay as just an id, and so extraction is retryable
        # without the client re-uploading the source file.
        def _download() -> bytes:
            response = self.client.get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"].read()

        try:
            return await asyncio.to_thread(_download)
        except Exception as exc:
            raise FileStorageError(f"Failed to download object: {key}") from exc

    async def get_presigned_url(self, key: str, expires_in_seconds: int = 60) -> str:
        try:
            return await asyncio.to_thread(
                self.client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in_seconds,
            )
        except Exception as exc:
            raise FileStorageError(f"Failed to create presigned URL: {key}") from exc

    async def get_presigned_put_url(self, key: str, content_type: str, expires_in_seconds: int = 900) -> str:
        # Signing is a local HMAC over the request parameters — no network call, so this
        # cannot fail on a slow or unreachable storage provider.
        try:
            return await asyncio.to_thread(
                self.client.generate_presigned_url,
                "put_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in_seconds,
            )
        except Exception as exc:
            raise FileStorageError(f"Failed to create presigned upload URL: {key}") from exc

    async def object_size(self, key: str) -> int | None:
        # HEAD, so the object's bytes are never transferred just to answer the question.
        try:
            response = await asyncio.to_thread(
                self.client.head_object, Bucket=self.bucket_name, Key=key
            )
            return int(response["ContentLength"])
        except self.client.exceptions.ClientError:
            # 404 (absent) and 403 (not visible to us) both mean "not usable here". Anything
            # else is a real storage failure and should not be swallowed, but boto3 folds
            # them into the same exception class, so this stays coarse.
            return None

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(
                self.client.delete_object, Bucket=self.bucket_name, Key=key
            )
        except Exception as exc:
            raise FileStorageError(f"Failed to delete object: {key}") from exc
