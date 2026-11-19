"""S3-compatible object storage (MinIO locally; docs/CONTENT_MANAGEMENT_ARCHITECTURE.md §5).

Binary media never goes through PostgreSQL or the API process: browsers upload with a short-lived
presigned PUT and play with a short-lived presigned GET. The API only signs URLs and inspects
uploaded objects. boto3 is synchronous, so every network call runs in a worker thread.

Two clients: `_ops` talks to the internal endpoint (e.g. http://minio:9000 on the compose
network); `_signer` signs URLs for the browser-facing endpoint (SigV4 signs the host).
"""

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings

PRESIGN_TTL_SECONDS = 300
_CHUNK = 1024 * 1024


class StorageUnavailableError(Exception):
    """Storage is not configured or did not respond. Never reported to users as success."""


@dataclass(frozen=True)
class ObjectInfo:
    size_bytes: int
    content_type: str | None
    head: bytes  # first bytes, for file-signature checks
    sha256: str


def _client(endpoint: str, settings: Settings) -> Any:
    secret = settings.s3_secret_access_key
    return boto3.client(
        "s3",
        endpoint_url=endpoint.rstrip("/"),
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=secret.get_secret_value() if secret else None,
        region_name=settings.s3_region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=3,
            read_timeout=30,
            retries={"max_attempts": 2},
        ),
    )


class ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        if not settings.media_storage_configured or settings.s3_endpoint_url is None:
            raise StorageUnavailableError("Object storage is not configured.")
        internal = str(settings.s3_endpoint_url)
        public = str(settings.s3_public_endpoint_url or settings.s3_endpoint_url)
        self.bucket = settings.s3_bucket
        self._ops = _client(internal, settings)
        self._signer = _client(public, settings)

    async def _call(self, fn: Any, /, **kwargs: Any) -> Any:
        try:
            return await asyncio.to_thread(fn, **kwargs)
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError(type(exc).__name__) from exc

    async def ensure_bucket(self) -> None:
        try:
            await asyncio.to_thread(self._ops.head_bucket, Bucket=self.bucket)
        except ClientError:
            await self._call(self._ops.create_bucket, Bucket=self.bucket)
        except BotoCoreError as exc:
            raise StorageUnavailableError(type(exc).__name__) from exc

    async def presign_put(self, key: str, content_type: str) -> str:
        url: str = await self._call(
            self._signer.generate_presigned_url,
            ClientMethod="put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=PRESIGN_TTL_SECONDS,
        )
        return url

    async def presign_get(
        self, key: str, content_type: str, *, ttl_seconds: int = PRESIGN_TTL_SECONDS
    ) -> str:
        url: str = await self._call(
            self._signer.generate_presigned_url,
            ClientMethod="get_object",
            Params={"Bucket": self.bucket, "Key": key, "ResponseContentType": content_type},
            ExpiresIn=ttl_seconds,
        )
        return url

    async def inspect(self, key: str, *, max_bytes: int) -> ObjectInfo | None:
        """Size, type, leading bytes and SHA-256 of an uploaded object (None if absent).
        Objects larger than `max_bytes` are reported by size without being read."""
        try:
            head = await asyncio.to_thread(self._ops.head_object, Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise StorageUnavailableError("ClientError") from exc
        except BotoCoreError as exc:
            raise StorageUnavailableError(type(exc).__name__) from exc
        size = int(head["ContentLength"])
        if size > max_bytes:
            return ObjectInfo(size, head.get("ContentType"), b"", "")

        def read() -> tuple[bytes, str]:
            body = self._ops.get_object(Bucket=self.bucket, Key=key)["Body"]
            digest = hashlib.sha256()
            first = b""
            for chunk in iter(lambda: body.read(_CHUNK), b""):
                if not first:
                    first = chunk[:64]
                digest.update(chunk)
            return first, digest.hexdigest()

        try:
            first, sha = await asyncio.to_thread(read)
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError(type(exc).__name__) from exc
        return ObjectInfo(size, head.get("ContentType"), first, sha)

    async def read(self, key: str, *, max_bytes: int) -> bytes:
        """Whole object (for server-side processing such as speech-to-text); bounded size."""

        def fetch() -> bytes:
            body = self._ops.get_object(Bucket=self.bucket, Key=key)["Body"]
            data = body.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise StorageUnavailableError("object too large")
            return bytes(data)

        try:
            return await asyncio.to_thread(fetch)
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailableError(type(exc).__name__) from exc

    async def delete(self, key: str) -> None:
        await self._call(self._ops.delete_object, Bucket=self.bucket, Key=key)
