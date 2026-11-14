"""Thin S3 adapter over boto3 (MinIO in this deployment; any S3 API works).

The rest of the code calls these functions and never touches boto3 directly, so
storage errors are translated in one place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.errors import ServiceUnavailableError

logger = logging.getLogger(__name__)


class StorageError(ServiceUnavailableError):
    code = "storage_unavailable"
    message = "Storage is temporarily unavailable"


@dataclass(frozen=True)
class ObjectInfo:
    size: int
    content_type: str | None


@dataclass(frozen=True)
class PresignedPost:
    url: str
    fields: dict[str, str]


@lru_cache
def get_client() -> BaseClient:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=60,
            # Only send/verify checksums when an operation requires them (S3-compatible
            # servers differ in support for the newer default integrity headers).
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def _is_not_found(exc: ClientError) -> bool:
    code = exc.response.get("Error", {}).get("Code", "")
    return code in {"404", "NoSuchKey", "NotFound"}


def presign_upload(
    bucket: str, key: str, *, content_type: str, max_bytes: int, expires_in: int
) -> PresignedPost:
    """Browser upload policy enforced by the storage server itself:
    exact key, exact Content-Type and a byte-size range."""
    try:
        post = get_client().generate_presigned_post(
            Bucket=bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_bytes],
            ],
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.error("Presign failed", exc_info=True)
        raise StorageError() from exc
    return PresignedPost(url=post["url"], fields=dict(post["fields"]))


def head(bucket: str, key: str) -> ObjectInfo | None:
    try:
        response = get_client().head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if _is_not_found(exc):
            return None
        raise StorageError() from exc
    except BotoCoreError as exc:
        raise StorageError() from exc
    return ObjectInfo(size=int(response["ContentLength"]), content_type=response.get("ContentType"))


def read_range(bucket: str, key: str, start: int, end: int) -> bytes:
    """Bytes [start, end] inclusive (used to sniff magic numbers)."""
    try:
        response = get_client().get_object(Bucket=bucket, Key=key, Range=f"bytes={start}-{end}")
        return response["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        raise StorageError() from exc


def put_bytes(bucket: str, key: str, data: bytes, *, content_type: str) -> None:
    try:
        get_client().put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    except (BotoCoreError, ClientError) as exc:
        raise StorageError() from exc


def upload_file(bucket: str, key: str, path: str, *, content_type: str) -> None:
    try:
        get_client().upload_file(path, bucket, key, ExtraArgs={"ContentType": content_type})
    except (BotoCoreError, ClientError) as exc:
        raise StorageError() from exc


def download_file(bucket: str, key: str, path: str) -> None:
    try:
        get_client().download_file(bucket, key, path)
    except (BotoCoreError, ClientError) as exc:
        raise StorageError() from exc


def delete(bucket: str, key: str) -> None:
    try:
        get_client().delete_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:
        raise StorageError() from exc


def delete_prefix(bucket: str, prefix: str) -> int:
    """Delete every object under `prefix`. Idempotent; returns the number deleted."""
    if not prefix or not prefix.endswith("/"):
        raise ValueError("prefix must be a non-empty 'directory' ending with '/'")
    client = get_client()
    deleted = 0
    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objects: list[dict[str, Any]] = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objects:
                client.delete_objects(Bucket=bucket, Delete={"Objects": objects, "Quiet": True})
                deleted += len(objects)
    except (BotoCoreError, ClientError) as exc:
        raise StorageError() from exc
    return deleted


def presign_get(bucket: str, key: str, *, expires_in: int) -> str:
    """Internal-only GET URL (signed for the internal endpoint; used by nginx X-Accel)."""
    try:
        return get_client().generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageError() from exc


def get_stream(bucket: str, key: str, byte_range: str | None = None) -> dict[str, Any]:
    """Raw get_object response (Body is a stream). Used by MEDIA_DELIVERY=proxy."""
    params: dict[str, Any] = {"Bucket": bucket, "Key": key}
    if byte_range:
        params["Range"] = byte_range
    try:
        return get_client().get_object(**params)
    except ClientError as exc:
        if _is_not_found(exc):
            raise
        raise StorageError() from exc
    except BotoCoreError as exc:
        raise StorageError() from exc


def is_reachable() -> bool:
    settings = get_settings()
    try:
        get_client().head_bucket(Bucket=settings.media_bucket)
    except (BotoCoreError, ClientError):
        logger.warning("Storage readiness check failed", exc_info=True)
        return False
    return True
