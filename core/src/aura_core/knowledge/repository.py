from __future__ import annotations

import json
from typing import Any

from .models import (
    KnowledgeConflict,
    KnowledgeFact,
    KnowledgeRecord,
    KnowledgeSource,
)


class KnowledgeRepository:
    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    async def initialize(self) -> None:
        from sqlalchemy import text

        statements = [
            """
            CREATE TABLE IF NOT EXISTS knowledge_sources (
                source_id TEXT PRIMARY KEY,
                uri TEXT NOT NULL,
                source_type TEXT NOT NULL,
                title TEXT,
                local_path TEXT,
                checksum_sha256 TEXT,
                discovered_at TIMESTAMPTZ NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_records (
                record_id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                content TEXT NOT NULL,
                source_id TEXT NOT NULL
                    REFERENCES knowledge_sources(source_id),
                kind TEXT NOT NULL,
                title TEXT,
                confidence DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_facts (
                fact_id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                confidence DOUBLE PRECISION NOT NULL,
                status TEXT NOT NULL,
                first_seen_at TIMESTAMPTZ NOT NULL,
                last_seen_at TIMESTAMPTZ NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_fact_evidence (
                fact_id TEXT NOT NULL
                    REFERENCES knowledge_facts(fact_id)
                    ON DELETE CASCADE,
                source_id TEXT NOT NULL
                    REFERENCES knowledge_sources(source_id),
                locator TEXT NOT NULL,
                quote TEXT,
                confidence DOUBLE PRECISION NOT NULL,
                PRIMARY KEY (fact_id, source_id, locator)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_record_facts (
                record_id TEXT NOT NULL
                    REFERENCES knowledge_records(record_id)
                    ON DELETE CASCADE,
                fact_id TEXT NOT NULL
                    REFERENCES knowledge_facts(fact_id)
                    ON DELETE CASCADE,
                PRIMARY KEY (record_id, fact_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_conflicts (
                conflict_id TEXT PRIMARY KEY,
                fact_a TEXT NOT NULL
                    REFERENCES knowledge_facts(fact_id),
                fact_b TEXT NOT NULL
                    REFERENCES knowledge_facts(fact_id),
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                resolution TEXT
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_knowledge_records_namespace
            ON knowledge_records(namespace)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_knowledge_facts_subject
            ON knowledge_facts(subject)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_knowledge_sources_checksum
            ON knowledge_sources(checksum_sha256)
            """,
        ]

        async with self.session_factory() as session:
            for statement in statements:
                await session.execute(text(statement))

            await session.commit()

    async def save_source(
        self,
        source: KnowledgeSource,
    ) -> None:
        from sqlalchemy import text

        query = text(
            """
            INSERT INTO knowledge_sources
            (
                source_id,
                uri,
                source_type,
                title,
                local_path,
                checksum_sha256,
                discovered_at,
                metadata
            )
            VALUES
            (
                :source_id,
                :uri,
                :source_type,
                :title,
                :local_path,
                :checksum_sha256,
                :discovered_at,
                CAST(:metadata AS JSONB)
            )
            ON CONFLICT (source_id)
            DO UPDATE SET
                title = EXCLUDED.title,
                local_path = EXCLUDED.local_path,
                checksum_sha256 = EXCLUDED.checksum_sha256,
                metadata = EXCLUDED.metadata
            """
        )

        async with self.session_factory() as session:
            await session.execute(
                query,
                {
                    "source_id": source.source_id,
                    "uri": source.uri,
                    "source_type": source.source_type,
                    "title": source.title,
                    "local_path": source.local_path,
                    "checksum_sha256": source.checksum_sha256,
                    "discovered_at": source.discovered_at,
                    "metadata": json.dumps(source.metadata),
                },
            )

            await session.commit()

    async def save_record(
        self,
        record: KnowledgeRecord,
    ) -> None:
        from sqlalchemy import text

        async with self.session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO knowledge_records
                    (
                        record_id,
                        namespace,
                        content,
                        source_id,
                        kind,
                        title,
                        confidence,
                        created_at,
                        updated_at,
                        metadata
                    )
                    VALUES
                    (
                        :record_id,
                        :namespace,
                        :content,
                        :source_id,
                        :kind,
                        :title,
                        :confidence,
                        :created_at,
                        :updated_at,
                        CAST(:metadata AS JSONB)
                    )
                    ON CONFLICT (record_id)
                    DO UPDATE SET
                        content = EXCLUDED.content,
                        confidence = EXCLUDED.confidence,
                        updated_at = EXCLUDED.updated_at,
                        metadata = EXCLUDED.metadata
                    """
                ),
                {
                    "record_id": record.record_id,
                    "namespace": record.namespace,
                    "content": record.content,
                    "source_id": record.source_id,
                    "kind": record.kind,
                    "title": record.title,
                    "confidence": record.confidence,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                    "metadata": json.dumps(record.metadata),
                },
            )

            for fact_id in record.facts:
                await session.execute(
                    text(
                        """
                        INSERT INTO knowledge_record_facts
                        (record_id, fact_id)
                        VALUES (:record_id, :fact_id)
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "record_id": record.record_id,
                        "fact_id": fact_id,
                    },
                )

            await session.commit()

    async def save_fact(
        self,
        fact: KnowledgeFact,
    ) -> None:
        from sqlalchemy import text

        async with self.session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO knowledge_facts
                    (
                        fact_id,
                        subject,
                        predicate,
                        object,
                        confidence,
                        status,
                        first_seen_at,
                        last_seen_at,
                        metadata
                    )
                    VALUES
                    (
                        :fact_id,
                        :subject,
                        :predicate,
                        :object,
                        :confidence,
                        :status,
                        :first_seen_at,
                        :last_seen_at,
                        CAST(:metadata AS JSONB)
                    )
                    ON CONFLICT (fact_id)
                    DO UPDATE SET
                        confidence = EXCLUDED.confidence,
                        status = EXCLUDED.status,
                        last_seen_at = EXCLUDED.last_seen_at,
                        metadata = EXCLUDED.metadata
                    """
                ),
                {
                    "fact_id": fact.fact_id,
                    "subject": fact.subject,
                    "predicate": fact.predicate,
                    "object": fact.object,
                    "confidence": fact.confidence,
                    "status": fact.status,
                    "first_seen_at": fact.first_seen_at,
                    "last_seen_at": fact.last_seen_at,
                    "metadata": json.dumps(fact.metadata),
                },
            )

            for evidence in fact.evidence:
                await session.execute(
                    text(
                        """
                        INSERT INTO knowledge_fact_evidence
                        (
                            fact_id,
                            source_id,
                            locator,
                            quote,
                            confidence
                        )
                        VALUES
                        (
                            :fact_id,
                            :source_id,
                            :locator,
                            :quote,
                            :confidence
                        )
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "fact_id": fact.fact_id,
                        "source_id": evidence.source_id,
                        "locator": evidence.locator,
                        "quote": evidence.quote,
                        "confidence": evidence.confidence,
                    },
                )

            await session.commit()

    async def save_conflict(
        self,
        conflict: KnowledgeConflict,
    ) -> None:
        from sqlalchemy import text

        async with self.session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO knowledge_conflicts
                    (
                        conflict_id,
                        fact_a,
                        fact_b,
                        reason,
                        status,
                        created_at,
                        resolution
                    )
                    VALUES
                    (
                        :conflict_id,
                        :fact_a,
                        :fact_b,
                        :reason,
                        :status,
                        :created_at,
                        :resolution
                    )
                    ON CONFLICT (conflict_id)
                    DO UPDATE SET
                        status = EXCLUDED.status,
                        resolution = EXCLUDED.resolution
                    """
                ),
                {
                    "conflict_id": conflict.conflict_id,
                    "fact_a": conflict.fact_a,
                    "fact_b": conflict.fact_b,
                    "reason": conflict.reason,
                    "status": conflict.status,
                    "created_at": conflict.created_at,
                    "resolution": conflict.resolution,
                },
            )

            await session.commit()

    async def find_facts(
        self,
        *,
        subject: str | None = None,
        predicate: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        from sqlalchemy import text

        async with self.session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT
                        fact_id,
                        subject,
                        predicate,
                        object,
                        confidence,
                        status,
                        metadata
                    FROM knowledge_facts
                    WHERE
                        (:subject IS NULL OR subject = :subject)
                        AND
                        (:predicate IS NULL OR predicate = :predicate)
                    ORDER BY
                        confidence DESC,
                        fact_id ASC
                    LIMIT :limit
                    """
                ),
                {
                    "subject": subject,
                    "predicate": predicate,
                    "limit": limit,
                },
            )

            return [
                dict(row)
                for row in result.mappings().all()
            ]
