from __future__ import annotations

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

    def upload(self, key: str, file_data: bytes | BinaryIO, content_type: str) -> str:
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=file_data,
                ContentType=content_type,
            )
            return key
        except Exception as exc:
            raise FileStorageError(f"Failed to upload object: {key}") from exc

    def download(self, key: str) -> bytes:
        # Read the whole object into memory. Used by the ingestion worker so the
        # queue payload can stay as just an id, and so extraction is retryable
        # without the client re-uploading the source file.
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"].read()
        except Exception as exc:
            raise FileStorageError(f"Failed to download object: {key}") from exc

    def get_presigned_url(self, key: str, expires_in_seconds: int = 900) -> str:
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expires_in_seconds,
            )
        except Exception as exc:
            raise FileStorageError(f"Failed to create presigned URL: {key}") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
        except Exception as exc:
            raise FileStorageError(f"Failed to delete object: {key}") from exc
