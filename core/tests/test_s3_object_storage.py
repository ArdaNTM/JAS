import asyncio

import httpx
import pytest

from aura_core.persistence.s3_object_storage import S3PresignedObjectStorage


class URLProvider:
    def __init__(self, url: str = "https://objects.example.test/bucket/key?signature=temporary") -> None:
        self.url = url
        self.operations: list[tuple[str, str]] = []

    def url_for(self, operation: str, key: str) -> str:
        self.operations.append((operation, key))
        return self.url


def test_s3_adapter_uses_presigned_urls_and_never_local_files() -> None:
    async def scenario() -> None:
        calls: list[tuple[str, str, bytes | None]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, str(request.url), request.content if request.method == "PUT" else None))
            if request.method == "GET":
                return httpx.Response(200, content=b"remote-object")
            return httpx.Response(200)

        provider = URLProvider()
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        storage = S3PresignedObjectStorage(provider, client=client)
        await storage.put("artifacts/run-1/result.json", b'{"ok":true}', content_type="application/json")
        assert await storage.get("artifacts/run-1/result.json") == b"remote-object"
        await storage.delete("artifacts/run-1/result.json")
        assert [call[0] for call in calls] == ["PUT", "GET", "DELETE"]
        assert all("artifacts/run-1/result.json" in call[1] for call in calls)
        assert calls[0][2] == b'{"ok":true}'
        assert provider.operations == [
            ("put", "artifacts/run-1/result.json"),
            ("get", "artifacts/run-1/result.json"),
            ("delete", "artifacts/run-1/result.json"),
        ]
        await client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize("key", ["", "../secret", "a/../secret", "/absolute", "a\\b"])
def test_s3_adapter_rejects_unsafe_object_keys(key: str) -> None:
    async def scenario() -> None:
        storage = S3PresignedObjectStorage(URLProvider())
        with pytest.raises(ValueError):
            await storage.get(key)
        await storage.close()

    asyncio.run(scenario())


def test_s3_adapter_rejects_non_https_signed_urls() -> None:
    async def scenario() -> None:
        storage = S3PresignedObjectStorage(URLProvider("http://objects.example.test/key"))
        with pytest.raises(ValueError, match="HTTPS"):
            await storage.get("key")
        await storage.close()

    asyncio.run(scenario())
