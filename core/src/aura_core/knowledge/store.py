from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import KnowledgeRecord, KnowledgeSource


class KnowledgeStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

        self.raw = self.root / "raw"
        self.normalized = self.root / "normalized"
        self.sources = self.root / "sources"
        self.knowledge = self.root / "knowledge"
        self.embeddings = self.root / "embeddings"
        self.indexes = self.root / "indexes"
        self.snapshots = self.root / "snapshots"
        self.manifests = self.root / "manifests"
        self.audit = self.root / "audit"
        self.logs = self.root / "logs"
        self.checkpoints = self.root / "checkpoints"

        for path in (
            self.raw,
            self.normalized,
            self.sources,
            self.knowledge,
            self.embeddings,
            self.indexes,
            self.snapshots,
            self.manifests,
            self.audit,
            self.logs,
            self.checkpoints,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def put_raw(
        self,
        source_id: str,
        data: bytes,
        suffix: str = ".bin",
    ) -> Path:
        digest = self.sha256(data)
        path = self.raw / f"{source_id}-{digest}{suffix}"

        if not path.exists():
            path.write_bytes(data)

        return path

    def put_source(
        self,
        source: KnowledgeSource,
        payload: bytes,
    ) -> KnowledgeSource:
        digest = self.sha256(payload)
        suffix = Path(source.uri).suffix or ".bin"

        path = self.put_raw(
            source.source_id,
            payload,
            suffix,
        )

        source.checksum_sha256 = digest
        source.local_path = str(path)

        return source

    def put_normalized(
        self,
        record: KnowledgeRecord,
    ) -> Path:
        path = self.normalized / f"{record.record_id}.json"

        payload = {
            "record_id": record.record_id,
            "namespace": record.namespace,
            "content": record.content,
            "source_id": record.source_id,
            "kind": record.kind,
            "title": record.title,
            "confidence": record.confidence,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "metadata": record.metadata,
            "facts": record.facts,
            "evidence": [
                {
                    "source_id": evidence.source_id,
                    "locator": evidence.locator,
                    "quote": evidence.quote,
                    "confidence": evidence.confidence,
                }
                for evidence in record.evidence
            ],
        }

        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return path

    def write_manifest(
        self,
        name: str,
        data: dict[str, Any],
    ) -> Path:
        path = self.manifests / f"{name}.json"

        path.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        return path
