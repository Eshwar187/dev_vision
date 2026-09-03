from typing import Any, Dict, Optional, Protocol
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("storage")
settings = get_settings()


class StorageService(Protocol):
    """Protocol defining S3-compatible object storage operations."""

    def check_health(self) -> bool:
        ...

    def ensure_bucket_exists(self) -> bool:
        ...

    def upload_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        ...

    def get_object_bytes(self, key: str) -> bytes:
        ...

    def generate_presigned_url(self, key: str, expiration: int = 900, method: str = "get_object") -> str:
        ...


class S3StorageService:
    """S3-compatible storage implementation using boto3 (MinIO or AWS S3)."""

    def __init__(self):
        self.bucket_name = settings.S3_BUCKET_NAME
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            use_ssl=settings.S3_SECURE,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def check_health(self) -> bool:
        """Verifies connection and access to the target bucket."""
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchBucket"):
                # Bucket doesn't exist, but endpoint is accessible
                return self.ensure_bucket_exists()
            logger.error("MinIO/S3 health check failed", error=str(e))
            return False
        except Exception as exc:
            logger.error("MinIO/S3 connection error", error=str(exc))
            return False

    def ensure_bucket_exists(self) -> bool:
        """Creates the default bucket if it does not already exist."""
        try:
            self.client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError:
            try:
                self.client.create_bucket(Bucket=self.bucket_name)
                logger.info("Created storage bucket", bucket=self.bucket_name)
                return True
            except Exception as e:
                logger.error("Failed to create storage bucket", error=str(e), bucket=self.bucket_name)
                return False

    def upload_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Uploads raw bytes to S3 and returns the object key."""
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    def get_object_bytes(self, key: str) -> bytes:
        """Retrieves raw bytes of an object from S3."""
        response = self.client.get_object(Bucket=self.bucket_name, Key=key)
        return response["Body"].read()

    def generate_presigned_url(self, key: str, expiration: int = 900, method: str = "get_object") -> str:
        """Generates a temporary presigned URL for secure direct client access."""
        return self.client.generate_presigned_url(
            ClientMethod=method,
            Params={"Bucket": self.bucket_name, "Key": key},
            ExpiresIn=expiration,
        )


_storage_instance: Optional[S3StorageService] = None


def get_storage() -> S3StorageService:
    """Returns singleton S3 storage service instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = S3StorageService()
    return _storage_instance
