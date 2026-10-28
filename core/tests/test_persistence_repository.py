import asyncio

import pytest

from aura_core.persistence.repository import InMemoryRepository, PersistedRecord


def test_in_memory_repository_increments_revision_and_copies_data() -> None:
    async def scenario() -> None:
        repository = InMemoryRepository()
        original = {"nested": {"value": 1}}
        first = await repository.save(PersistedRecord("task", "task-1", original))
        original["nested"]["value"] = 2
        assert first.revision == 1
        assert first.data["nested"]["value"] == 1

        second = await repository.save(PersistedRecord("task", "task-1", {"state": "done"}))
        assert second.revision == 2
        assert (await repository.get("task", "task-1")) == second

    asyncio.run(scenario())


def test_in_memory_repository_scopes_by_entity_type() -> None:
    async def scenario() -> None:
        repository = InMemoryRepository()
        await repository.save(PersistedRecord("task", "same-id", {"value": 1}))
        await repository.save(PersistedRecord("workflow", "same-id", {"value": 2}))
        assert (await repository.get("task", "same-id")).data == {"value": 1}
        assert (await repository.get("workflow", "same-id")).data == {"value": 2}

    asyncio.run(scenario())


def test_postgresql_repository_rejects_missing_or_non_postgres_url() -> None:
    from aura_core.persistence.repository import PostgreSQLRepository

    with pytest.raises(ValueError, match="AURA_DATABASE_URL is required"):
        PostgreSQLRepository("")
    with pytest.raises(ValueError, match="must use PostgreSQL"):
        PostgreSQLRepository("sqlite:///should-not-be-used.db")
