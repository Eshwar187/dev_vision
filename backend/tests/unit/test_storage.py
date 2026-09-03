from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
from app.core.storage import S3StorageService


def test_storage_health_success():
    with patch("boto3.client") as mock_boto:
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        mock_s3.head_bucket.return_value = {}

        storage = S3StorageService()
        assert storage.check_health() is True
        mock_s3.head_bucket.assert_called_once()


def test_storage_health_failure():
    with patch("boto3.client") as mock_boto:
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        mock_s3.head_bucket.side_effect = Exception("Connection refused")

        storage = S3StorageService()
        assert storage.check_health() is False
