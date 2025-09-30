from datetime import timedelta
from urllib.parse import urlparse
from minio import Minio
from .settings import Settings


def get_minio_client(settings: Settings) -> Minio:
    endpoint = settings.minio_endpoint
    if endpoint.startswith("http://"):
        endpoint = endpoint[len("http://"):]
    if endpoint.startswith("https://"):
        endpoint = endpoint[len("https://"):]
    client = Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    return client


def ensure_bucket(client: Minio, bucket: str):
    found = client.bucket_exists(bucket)
    if not found:
        client.make_bucket(bucket)


def upload_bytes(client: Minio, bucket: str, key: str, data: bytes, content_type: str | None = None):
    from io import BytesIO
    bio = BytesIO(data)
    client.put_object(bucket, key, bio, length=len(data), content_type=content_type)


def _rewrite_public(url: str, settings: Settings) -> str:
    if not settings.public_minio_url:
        return url
    try:
        src = urlparse(url)
        pub = urlparse(settings.public_minio_url)
        # keep path and query, swap scheme+netloc
        return f"{pub.scheme}://{pub.netloc}{src.path}?{src.query}" if src.query else f"{pub.scheme}://{pub.netloc}{src.path}"
    except Exception:
        return url


def presigned_get_object(client: Minio, bucket: str, key: str | None, expiry_seconds: int = 3600) -> str | None:
    if not key:
        return None
    try:
        # MinIO Python SDK requires datetime.timedelta for expires per newer versions
        url = client.presigned_get_object(bucket, key, expires=timedelta(seconds=expiry_seconds))
        # optional public rewrite for browser-accessible host
        from .settings import get_settings
        return _rewrite_public(url, get_settings())
    except Exception:
        return None


