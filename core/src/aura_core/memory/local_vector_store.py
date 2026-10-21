"""Principal-scoped SQLite vector memory with local cosine retrieval."""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from aura_core.memory.local_embeddings import VectorEmbedder


class LocalVectorMemory:
    def __init__(self, database_path: str | Path, embedder: VectorEmbedder) -> None:
        self.database_path = str(database_path)
        self.embedder = embedder
        Path(self.database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS local_vector_memory (
                    memory_id TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_local_vector_principal ON local_vector_memory(principal_id, created_at DESC)")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    async def remember(self, *, principal_id: str, content: str, tags: list[str] | None = None) -> str:
        principal_id = principal_id.strip()
        content = content.strip()
        if not principal_id or len(principal_id) > 128:
            raise ValueError("principal_id must contain 1..128 characters")
        if not content or len(content) > 12000:
            raise ValueError("content must contain 1..12000 characters")
        clean_tags = [str(tag).strip()[:80] for tag in (tags or [])[:32] if str(tag).strip()]
        vectors = await self.embedder.embed([content])
        if len(vectors) != 1 or not vectors[0]:
            raise ValueError("embedder must return one non-empty vector")
        if any(not math.isfinite(value) for value in vectors[0]):
            raise ValueError("embedding contains a non-finite value")
        memory_id = str(uuid4())
        with self._connect() as db:
            db.execute(
                "INSERT INTO local_vector_memory VALUES (?, ?, ?, ?, ?, ?, ?)",
                (memory_id, principal_id, content, json.dumps(clean_tags, ensure_ascii=False),
                 json.dumps(vectors[0]), self.embedder.model, datetime.now(UTC).isoformat()),
            )
        return memory_id

    async def recall(self, *, principal_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        principal_id = principal_id.strip()
        if not principal_id or not query.strip() or len(query) > 12000:
            return []
        limit = min(max(int(limit), 1), 50)
        query_vectors = await self.embedder.embed([query])
        if len(query_vectors) != 1 or not query_vectors[0]:
            return []
        q = query_vectors[0]
        ranked: list[tuple[float, sqlite3.Row]] = []
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM local_vector_memory WHERE principal_id = ? ORDER BY created_at DESC LIMIT 5000",
                (principal_id,),
            ).fetchall()
        for row in rows:
            if row["model_id"] != self.embedder.model:
                continue
            vector = json.loads(row["vector_json"])
            if len(vector) != len(q):
                continue
            dot = sum(float(a) * float(b) for a, b in zip(q, vector))
            norm_q = math.sqrt(sum(float(a) ** 2 for a in q))
            norm_v = math.sqrt(sum(float(a) ** 2 for a in vector))
            score = dot / (norm_q * norm_v) if norm_q and norm_v else 0.0
            ranked.append((score, row))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [{
            "memory_id": row["memory_id"], "principal_id": row["principal_id"],
            "content": row["content"], "tags": json.loads(row["tags_json"]),
            "score": round(score, 6), "model": row["model_id"],
            "trust": "untrusted_reference_data",
        } for score, row in ranked[:limit]]
