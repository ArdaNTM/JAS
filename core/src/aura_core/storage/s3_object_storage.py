"""Dependency-free S3-compatible object storage with SigV4 and presigned URLs.

The adapter uses path-style requests so it works with AWS S3 and compatible
services such as MinIO. It stores opaque task/checkpoint artifacts only; it
never executes tools or makes authorization decisions.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


class ObjectStorageError(RuntimeError):
    """An S3-compatible operation failed."""


class S3ObjectStorage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
        session_token: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        parsed = urlsplit(endpoint_url.rstrip("/"))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("endpoint_url must be an absolute HTTP(S) URL")
        if not bucket or "/" in bucket or bucket in {".", ".."}:
            raise ValueError("bucket must be a non-empty bucket name")
        if not access_key or not secret_key or not region:
            raise ValueError("S3 credentials and region are required")
        if not 0 < timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be between 0 and 120")
        self.endpoint_url = endpoint_url.rstrip("/")
        self._parsed = parsed
        self.bucket = bucket
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.session_token = session_token
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "S3ObjectStorage":
        return cls(
            endpoint_url=os.environ["AURA_OBJECT_STORAGE_ENDPOINT"],
            bucket=os.environ["AURA_OBJECT_STORAGE_BUCKET"],
            access_key=os.environ["AURA_OBJECT_STORAGE_ACCESS_KEY"],
            secret_key=os.environ["AURA_OBJECT_STORAGE_SECRET_KEY"],
            region=os.getenv("AURA_OBJECT_STORAGE_REGION", "us-east-1"),
            session_token=os.getenv("AURA_OBJECT_STORAGE_SESSION_TOKEN"),
        )

    def head_bucket(self) -> None:
        """Verify bucket reachability and credentials using an authenticated S3 HEAD."""
        self._request("HEAD", "")

    def put_bytes(self, key: str, body: bytes, *, content_type: str = "application/octet-stream") -> None:
        if not isinstance(body, bytes):
            raise TypeError("body must be bytes")
        self._request("PUT", key, body, {"content-type": content_type})

    def get_bytes(self, key: str) -> bytes:
        return self._request("GET", key)

    def delete(self, key: str) -> None:
        self._request("DELETE", key)

    def create_presigned_get_url(self, key: str, *, expires_in: int = 300) -> str:
        key = self._validate_key(key)
        if type(expires_in) is not int or not 1 <= expires_in <= 604800:
            raise ValueError("expires_in must be an integer from 1 to 604800 seconds")
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date = now.strftime("%Y%m%d")
        scope = f"{date}/{self.region}/s3/aws4_request"
        path = self._path(key)
        params = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{self.access_key}/{scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(expires_in),
            "X-Amz-SignedHeaders": "host",
        }
        if self.session_token:
            params["X-Amz-Security-Token"] = self.session_token
        canonical_query = self._canonical_query(params)
        canonical_request = "\n".join([
            "GET", path, canonical_query, f"host:{self._parsed.netloc}\n",
            "host", "UNSIGNED-PAYLOAD",
        ])
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256", amz_date, scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])
        signature = hmac.new(
            self._signing_key(date), string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
        return f"{self.endpoint_url}{path}?{canonical_query}&X-Amz-Signature={signature}"

    def _request(self, method: str, key: str, body: bytes = b"", headers: dict[str, str] | None = None) -> bytes:
        if key:
            key = self._validate_key(key)
        elif method != "HEAD":
            raise ValueError("An empty key is permitted only for bucket HEAD")
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date = now.strftime("%Y%m%d")
        path = f"/{quote(self.bucket, safe='-_.~')}" if not key else self._path(key)
        payload_hash = hashlib.sha256(body).hexdigest()
        request_headers = {
            "host": self._parsed.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if self.session_token:
            request_headers["x-amz-security-token"] = self.session_token
        for name, value in (headers or {}).items():
            request_headers[name.lower()] = value.strip()
        signed_names = ";".join(sorted(request_headers))
        canonical_headers = "".join(f"{name}:{' '.join(value.split())}\n" for name, value in sorted(request_headers.items()))
        canonical_request = "\n".join([
            method, path, "", canonical_headers, signed_names, payload_hash,
        ])
        scope = f"{date}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256", amz_date, scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])
        signature = hmac.new(
            self._signing_key(date), string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
        authorization = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_names}, Signature={signature}"
        )
        headers_out = {name: value for name, value in request_headers.items()}
        headers_out["authorization"] = authorization
        request = Request(
            f"{self.endpoint_url}{path}", data=body if method in {"PUT", "POST"} else None,
            headers=headers_out, method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read()
        except HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise ObjectStorageError(f"S3 {method} failed with HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ObjectStorageError(f"S3 {method} request failed") from exc

    def _signing_key(self, date: str) -> bytes:
        key_date = hmac.new(("AWS4" + self.secret_key).encode(), date.encode(), hashlib.sha256).digest()
        key_region = hmac.new(key_date, self.region.encode(), hashlib.sha256).digest()
        key_service = hmac.new(key_region, b"s3", hashlib.sha256).digest()
        return hmac.new(key_service, b"aws4_request", hashlib.sha256).digest()

    def _path(self, key: str) -> str:
        return f"/{quote(self.bucket, safe='-_.~')}/{quote(key, safe='/-_.~')}"

    @staticmethod
    def _canonical_query(params: dict[str, str]) -> str:
        return urlencode(sorted(params.items()), quote_via=quote, safe="-_.~")

    @staticmethod
    def _validate_key(key: str) -> str:
        if not isinstance(key, str) or not key or len(key) > 1024:
            raise ValueError("object key must be a non-empty string of at most 1024 characters")
        if key.startswith("/") or "\\" in key or any(part in {".", ".."} for part in key.split("/")):
            raise ValueError("object key must be a normalized relative path")
        if any(ord(char) < 32 for char in key):
            raise ValueError("object key contains control characters")
        return key
