import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

sys.modules.setdefault("boto3", SimpleNamespace(client=Mock()))

from src.core.exceptions import FileStorageError
from src.infrastructure.storage.filebase_adapter import FilebaseAdapter


class FilebaseAdapterTest(TestCase):
    def setUp(self) -> None:
        self.settings = SimpleNamespace(
            filebase_bucket_name="bucket",
            filebase_endpoint="https://s3.filebase.io",
            filebase_access_key="access",
            filebase_secret_key="secret",
        )

    @patch("src.infrastructure.storage.filebase_adapter.boto3.client")
    def test_upload_returns_existing_key(self, client_factory: Mock) -> None:
        client = Mock()
        client_factory.return_value = client
        adapter = FilebaseAdapter(self.settings)

        key = adapter.upload("user/asset/file.pdf", b"pdf", "application/pdf")

        self.assertEqual(key, "user/asset/file.pdf")
        client.put_object.assert_called_once_with(
            Bucket="bucket",
            Key="user/asset/file.pdf",
            Body=b"pdf",
            ContentType="application/pdf",
        )
        client_factory.assert_called_once_with(
            "s3",
            endpoint_url="https://s3.filebase.io",
            region_name="us-east-1",
            aws_access_key_id="access",
            aws_secret_access_key="secret",
        )

    @patch("src.infrastructure.storage.filebase_adapter.boto3.client")
    def test_presigned_url_uses_get_object(self, client_factory: Mock) -> None:
        client = Mock()
        client.generate_presigned_url.return_value = "https://signed"
        client_factory.return_value = client
        adapter = FilebaseAdapter(self.settings)

        url = adapter.get_presigned_url("user/asset/file.pdf", 60)

        self.assertEqual(url, "https://signed")
        client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "bucket", "Key": "user/asset/file.pdf"},
            ExpiresIn=60,
        )

    @patch("src.infrastructure.storage.filebase_adapter.boto3.client")
    def test_delete_wraps_storage_errors(self, client_factory: Mock) -> None:
        client = Mock()
        client.delete_object.side_effect = RuntimeError("boom")
        client_factory.return_value = client
        adapter = FilebaseAdapter(self.settings)

        with self.assertRaises(FileStorageError):
            adapter.delete("user/asset/file.pdf")
