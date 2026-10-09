import os
import time
from pathlib import Path
from urllib.parse import quote

from ..config import get_settings
from .security import sign

EXT_MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "heic": "image/heic", "pdf": "application/pdf"}


class LocalStorage:
    def __init__(self):
        self.root = Path(get_settings().local_storage_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError("bad key")
        return p

    def put(self, key: str, data: bytes, mime: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def signed_url(self, key: str) -> str:
        st = get_settings()
        exp = int(time.time()) + st.signed_url_seconds
        sig = sign(f"{key}:{exp}")
        return f"{st.public_api_url}/api/v1/files?k={quote(key)}&exp={exp}&sig={sig}"


class S3Storage:
    def __init__(self):
        import boto3
        st = get_settings()
        self.bucket = st.s3_bucket
        kw = dict(endpoint_url=st.s3_endpoint_url, aws_access_key_id=st.s3_access_key,
                  aws_secret_access_key=st.s3_secret_key, region_name=st.s3_region)
        self.client = boto3.client("s3", **kw)
        self.signer = boto3.client("s3", **{**kw, "endpoint_url": st.s3_public_endpoint_url or st.s3_endpoint_url})
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key, data, mime):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime)

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def signed_url(self, key):
        return self.signer.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=get_settings().signed_url_seconds)


_storage = None


def get_storage():
    global _storage
    if _storage is None:
        _storage = S3Storage() if get_settings().storage_backend == "s3" else LocalStorage()
    return _storage


def reset_storage():
    global _storage
    _storage = None
