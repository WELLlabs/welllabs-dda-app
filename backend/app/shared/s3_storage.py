"""S3 storage for per-project media and QField package artifacts."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.shared.config import settings

logger = logging.getLogger(__name__)

PRESIGN_TTL = 3600


def is_s3_enabled() -> bool:
    return bool(settings.aws_s3_bucket)


def s3_client():
    region = settings.aws_default_region
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
    )


def media_key(project_id: str, filename: str) -> str:
    return f"{project_id}/media/{filename}"


def packages_prefix(project_id: str) -> str:
    return f"{project_id}/packages/"


def project_prefix(project_id: str) -> str:
    return f"{project_id}/"


def object_exists(key: str) -> bool:
    if not is_s3_enabled():
        return False
    try:
        s3_client().head_object(Bucket=settings.aws_s3_bucket, Key=key)
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def upload_bytes(key: str, data: bytes, content_type: str | None = None) -> None:
    if not is_s3_enabled():
        raise RuntimeError("AWS_S3_BUCKET is not configured")
    extra = {}
    if content_type:
        extra["ContentType"] = content_type
    s3_client().put_object(Bucket=settings.aws_s3_bucket, Key=key, Body=data, **extra)


async def upload_bytes_async(key: str, data: bytes, content_type: str | None = None) -> None:
    """Non-blocking S3 put for use inside async FastAPI routes."""
    if not is_s3_enabled():
        raise RuntimeError("AWS_S3_BUCKET is not configured")
    import aioboto3

    region = settings.aws_default_region
    session = aioboto3.Session()
    extra = {}
    if content_type:
        extra["ContentType"] = content_type
    async with session.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
    ) as client:
        await client.put_object(Bucket=settings.aws_s3_bucket, Key=key, Body=data, **extra)


def upload_file(local_path: Path, key: str) -> None:
    if not is_s3_enabled():
        raise RuntimeError("AWS_S3_BUCKET is not configured")
    content_type, _ = mimetypes.guess_type(str(local_path))
    extra = {"ExtraArgs": {"ContentType": content_type}} if content_type else {}
    s3_client().upload_file(str(local_path), settings.aws_s3_bucket, key, **extra)


def sync_directory_to_s3(local_dir: Path, s3_prefix: str) -> list[str]:
    """Upload all files under local_dir to s3_prefix, preserving relative paths."""
    if not is_s3_enabled():
        return []
    if not s3_prefix.endswith("/"):
        s3_prefix += "/"

    uploaded: list[str] = []
    for path in local_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(local_dir).as_posix()
        key = f"{s3_prefix}{rel}"
        try:
            upload_file(path, key)
            uploaded.append(key)
            logger.info("Uploaded s3://%s/%s", settings.aws_s3_bucket, key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "S3Error")
            logger.warning("S3 package upload failed (%s) for %s", code, key)
    return uploaded


def presigned_get_url(key: str, expires_in: int = PRESIGN_TTL) -> str:
    if not is_s3_enabled():
        raise RuntimeError("AWS_S3_BUCKET is not configured")
    return s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.aws_s3_bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def get_object_bytes(key: str) -> bytes:
    if not is_s3_enabled():
        raise RuntimeError("AWS_S3_BUCKET is not configured")
    resp = s3_client().get_object(Bucket=settings.aws_s3_bucket, Key=key)
    return resp["Body"].read()


def delete_object(key: str) -> None:
    if not is_s3_enabled():
        return
    try:
        s3_client().delete_object(Bucket=settings.aws_s3_bucket, Key=key)
    except ClientError as exc:
        logger.warning("Failed to delete s3://%s/%s: %s", settings.aws_s3_bucket, key, exc)


def list_keys(prefix: str) -> list[str]:
    """Return all object keys under prefix."""
    if not is_s3_enabled():
        return []
    if not prefix.endswith("/"):
        prefix += "/"
    client = s3_client()
    paginator = client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=settings.aws_s3_bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def delete_keys(keys: list[str]) -> int:
    """Batch-delete a list of S3 keys. Returns count deleted."""
    if not is_s3_enabled() or not keys:
        return 0
    client = s3_client()
    deleted = 0
    for i in range(0, len(keys), 1000):
        batch = [{"Key": k} for k in keys[i : i + 1000]]
        client.delete_objects(Bucket=settings.aws_s3_bucket, Delete={"Objects": batch})
        deleted += len(batch)
    logger.info("Deleted %d object(s) from S3", deleted)
    return deleted


def delete_prefix(prefix: str) -> int:
    """Delete all objects under prefix. Returns count deleted."""
    if not is_s3_enabled():
        return 0
    if not prefix.endswith("/"):
        prefix += "/"

    client = s3_client()
    deleted = 0
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.aws_s3_bucket, Prefix=prefix):
        objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if not objects:
            continue
        client.delete_objects(Bucket=settings.aws_s3_bucket, Delete={"Objects": objects})
        deleted += len(objects)
    if deleted:
        logger.info("Deleted %d object(s) under s3://%s/%s", deleted, settings.aws_s3_bucket, prefix)
    return deleted
