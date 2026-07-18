"""S3-compatible object storage client (aioboto3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, BinaryIO

import aioboto3
from botocore.config import Config

from pycommon.config import StorageSettings


@dataclass
class ObjectStorageClient:
    """Thin async wrapper around S3 API — works with SeaweedFS, AWS S3, Ceph RGW, etc."""

    settings: StorageSettings
    _session: aioboto3.Session | None = None

    def __post_init__(self) -> None:
        self._session = aioboto3.Session()

    def _client_kwargs(self) -> dict[str, Any]:
        return {
            "service_name": "s3",
            "endpoint_url": self.settings.endpoint_url,
            "aws_access_key_id": self.settings.access_key,
            "aws_secret_access_key": self.settings.secret_key,
            "region_name": self.settings.region,
            "config": Config(
                s3={"addressing_style": "path" if self.settings.use_path_style else "virtual"},
                signature_version="s3v4",
            ),
        }

    async def ensure_bucket(self, bucket: str | None = None) -> None:
        bucket = bucket or self.settings.bucket
        async with self._session.client(**self._client_kwargs()) as client:  # type: ignore[union-attr]
            try:
                await client.head_bucket(Bucket=bucket)
            except Exception:
                await client.create_bucket(Bucket=bucket)

    async def put_object(
        self,
        key: str,
        body: bytes | BinaryIO,
        *,
        content_type: str = "application/octet-stream",
        bucket: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        bucket = bucket or self.settings.bucket
        async with self._session.client(**self._client_kwargs()) as client:  # type: ignore[union-attr]
            await client.put_object(
                Bucket=bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                Metadata=metadata or {},
            )
        return key

    async def delete_object(self, key: str, *, bucket: str | None = None) -> None:
        bucket = bucket or self.settings.bucket
        async with self._session.client(**self._client_kwargs()) as client:  # type: ignore[union-attr]
            await client.delete_object(Bucket=bucket, Key=key)

    async def get_presigned_url(
        self,
        key: str,
        *,
        method: str = "get_object",
        expires_in: int = 3600,
        bucket: str | None = None,
        content_type: str | None = None,
    ) -> str:
        bucket = bucket or self.settings.bucket
        params: dict[str, Any] = {"Bucket": bucket, "Key": key}
        if content_type and method == "put_object":
            params["ContentType"] = content_type
        async with self._session.client(**self._client_kwargs()) as client:  # type: ignore[union-attr]
            return await client.generate_presigned_url(
                ClientMethod=method,
                Params=params,
                ExpiresIn=expires_in,
            )

    async def get_object_bytes(self, key: str, *, bucket: str | None = None) -> bytes:
        bucket = bucket or self.settings.bucket
        async with self._session.client(**self._client_kwargs()) as client:  # type: ignore[union-attr]
            resp = await client.get_object(Bucket=bucket, Key=key)
            async with resp["Body"] as stream:
                return await stream.read()
