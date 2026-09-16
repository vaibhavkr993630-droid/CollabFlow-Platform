import uuid

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

settings = get_settings()

_client = None


def get_s3_client():
    """
    Module-level singleton, same reasoning as get_redis_client()/engine: boto3
    clients are safe to share across requests (thread-safe, manage their own
    connection pool under the hood) — no need to build a new one per call.
    """
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            # region_name is meaningless to MinIO but required here: without it,
            # boto3 tries to resolve a region via the EC2 instance metadata service
            # (169.254.169.254) before falling back, which hangs for a long time
            # (not a quick failure) in any environment where that address is
            # unreachable — every non-EC2 environment, including local dev/CI.
            region_name="us-east-1",
            config=Config(signature_version="s3v4"),
        )
    return _client


def ensure_bucket_exists() -> None:
    """Called once from main.py's lifespan on startup — idempotent, so it's safe to
    call every time the app boots rather than requiring a separate provisioning step."""
    client = get_s3_client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in ("404", "NoSuchBucket"):
            client.create_bucket(Bucket=settings.s3_bucket)
        else:
            raise


def build_storage_key(task_id: uuid.UUID, filename: str) -> str:
    # Strip any path components from the client-supplied filename first — an
    # object key built from "../../etc/passwd" or "a/b/c" would otherwise nest
    # into (or escape) unintended "directories" within the bucket's key namespace.
    safe_filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    # Prefixed by a fresh UUID, not just task_id/filename: two uploads of the same
    # filename to the same task must not collide/overwrite each other in the bucket.
    return f"tasks/{task_id}/{uuid.uuid4().hex}_{safe_filename}"


def upload_bytes(*, key: str, data: bytes, content_type: str) -> None:
    get_s3_client().put_object(
        Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type
    )


def delete_object(*, key: str) -> None:
    get_s3_client().delete_object(Bucket=settings.s3_bucket, Key=key)


def generate_presigned_download_url(*, key: str, filename: str, expires_in: int = 300) -> str:
    return get_s3_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=expires_in,
    )
