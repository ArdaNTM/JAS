from __future__ import annotations

from typing import Any

import httpx

from .models import (
    MemoryQuery,
    MemoryRecord,
    MemorySearchResult,
)
from .embeddings import EmbeddingProvider


class SemanticMemoryStore:
    def __init__(
        self,
        *,
        embeddings: EmbeddingProvider,
        qdrant_url: str = "http://127.0.0.1:6333",
        collection: str = "aura_memory",
        timeout: float = 30.0,
    ) -> None:
        self.embeddings = embeddings
        self.qdrant_url = qdrant_url.rstrip("/")
        self.collection = collection
        self.timeout = timeout
        self._dimension: int | None = None

    async def initialize(self) -> None:
        embeddings = await self.embeddings.embed(
            ["AURA semantic memory bootstrap"]
        )

        if not embeddings:
            raise RuntimeError(
                "Embedding provider returned no vector"
            )

        dimension = embeddings[0].dimensions

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:

            response = await client.get(
                f"{self.qdrant_url}/collections/{self.collection}"
            )

            if response.status_code == 404:
                create = await client.put(
                    f"{self.qdrant_url}/collections/{self.collection}",
                    json={
                        "vectors": {
                            "size": dimension,
                            "distance": "Cosine",
                        }
                    },
                )

                create.raise_for_status()

            else:
                response.raise_for_status()

                payload = response.json()

                vectors = (
                    payload
                    .get("result", {})
                    .get("config", {})
                    .get("params", {})
                    .get("vectors", {})
                )

                if (
                    isinstance(vectors, dict)
                    and "size" in vectors
                ):
                    existing_dimension = int(
                        vectors["size"]
                    )

                    if existing_dimension != dimension:
                        raise RuntimeError(
                            "Qdrant vector dimension mismatch: "
                            f"collection={existing_dimension}, "
                            f"embedding={dimension}"
                        )

        self._dimension = dimension

    async def put(
        self,
        record: MemoryRecord,
    ) -> None:
        if self._dimension is None:
            await self.initialize()

        embedding = (
            await self.embeddings.embed(
                [record.content]
            )
        )[0]

        payload: dict[str, Any] = {
            "record_id": record.record_id,
            "namespace": record.namespace,
            "content": record.content,
            "source": record.source,
            "metadata": record.metadata,
            "created_at": record.created_at.isoformat(),
        }

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:
            response = await client.put(
                (
                    f"{self.qdrant_url}"
                    f"/collections/{self.collection}"
                    "/points"
                ),
                json={
                    "points": [
                        {
                            "id": record.record_id,
                            "vector": embedding.vector,
                            "payload": payload,
                        }
                    ]
                },
            )

            response.raise_for_status()

    async def search(
        self,
        query: MemoryQuery,
    ) -> list[MemorySearchResult]:
        if self._dimension is None:
            await self.initialize()

        embedding = (
            await self.embeddings.embed(
                [query.text]
            )
        )[0]

        must: list[dict[str, Any]] = [
            {
                "key": "namespace",
                "match": {
                    "value": query.namespace,
                },
            }
        ]

        for key, value in sorted(
            query.metadata.items()
        ):
            must.append(
                {
                    "key": f"metadata.{key}",
                    "match": {
                        "value": value,
                    },
                }
            )

        async with httpx.AsyncClient(
            timeout=self.timeout
        ) as client:
            response = await client.post(
                (
                    f"{self.qdrant_url}"
                    f"/collections/{self.collection}"
                    "/points/query"
                ),
                json={
                    "query": embedding.vector,
                    "limit": max(
                        1,
                        min(query.limit, 100),
                    ),
                    "with_payload": True,
                    "filter": {
                        "must": must,
                    },
                },
            )

            response.raise_for_status()

            payload = response.json()

        result = payload.get("result", {})
        points = (
            result.get("points", [])
            if isinstance(result, dict)
            else []
        )

        results: list[MemorySearchResult] = []

        from datetime import datetime, timezone

        for hit in points:
            data = hit.get("payload") or {}

            created_value = data.get(
                "created_at"
            )

            try:
                created_at = (
                    datetime.fromisoformat(
                        created_value
                    )
                    if created_value
                    else datetime.now(timezone.utc)
                )
            except ValueError:
                created_at = datetime.now(
                    timezone.utc
                )

            results.append(
                MemorySearchResult(
                    record=MemoryRecord(
                        record_id=str(
                            data.get(
                                "record_id",
                                hit["id"],
                            )
                        ),
                        namespace=str(
                            data.get(
                                "namespace",
                                query.namespace,
                            )
                        ),
                        content=str(
                            data.get(
                                "content",
                                "",
                            )
                        ),
                        source=str(
                            data.get(
                                "source",
                                "",
                            )
                        ),
                        metadata=dict(
                            data.get(
                                "metadata"
                            )
                            or {}
                        ),
                        created_at=created_at,
                    ),
                    score=float(
                        hit.get(
                            "score",
                            0.0,
                        )
                    ),
                )
            )

        return results
