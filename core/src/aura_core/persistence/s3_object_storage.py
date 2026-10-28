"""S3-compatible object access through short-lived pre-signed URLs.

Signing and credential management deliberately stay in a trusted signer/secret
manager. This adapter accepts only HTTPS URLs supplied by that signer, does not
persist credentials, and never falls back to local files.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from aura_core.persistence.storage_interfaces import ObjectStorage, PresignedURLProvider


class S3PresignedObjectStorage:
    def __init__(
        self,
        urls: PresignedURLProvider,
        *,
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._urls = urls
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False)
        self._owns_client = client is None

    def _url(self, operation: str, key: str) -> str:
        if not isinstance(key, str) or not key.strip() or key.startswith("/") or "\\" in key:
            raise ValueError("key must be a non-empty relative object key")
        if any(part in (".", "..") for part in key.split("/")):
            raise ValueError("key must not contain dot path segments")
        url = self._urls.url_for(operation, key)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("presigned object URLs must use HTTPS and contain no userinfo")
        return url

    async def put(self, key: str, body: bytes, *, content_type: str = "application/octet-stream") -> None:
        if not isinstance(body, bytes):
            raise TypeError("body must be bytes")
        if not content_type or "\r" in content_type or "\n" in content_type:
            raise ValueError("content_type is invalid")
        response = await self._client.put(
            self._url("put", key), content=body, headers={"Content-Type": content_type}
        )
        response.raise_for_status()

    async def get(self, key: str) -> bytes:
        response = await self._client.get(self._url("get", key))
        response.raise_for_status()
        return response.content

    async def delete(self, key: str) -> None:
        response = await self._client.delete(self._url("delete", key))
        response.raise_for_status()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
