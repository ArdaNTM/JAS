"""Scoped graph deletion is explicitly confirmed, bounded and idempotent."""
import asyncio

import pytest

from aura_core.memory.graph_store import SQLiteGraphStore, PostgreSQLGraphStore


def test_sqlite_delete_is_scoped_idempotent_and_durable(tmp_path):
    async def scenario():
        path = tmp_path / "graph.sqlite"
        store = SQLiteGraphStore(path)
        alice = await store.insert(principal_id="alice", subject="a", predicate="rel", object="b")
        bob = await store.insert(principal_id="bob", subject="a", predicate="rel", object="private")
        with pytest.raises(PermissionError):
            await store.delete_fact(principal_id="alice", fact_id=alice)
        with pytest.raises(PermissionError):
            await store.delete_fact(principal_id="alice", fact_id=alice, confirmed=1)
        assert await store.delete_fact(principal_id="bob", fact_id=alice, confirmed=True) is False
        assert await store.delete_fact(principal_id="alice", fact_id=alice, confirmed=True)
        assert not await store.delete_fact(principal_id="alice", fact_id=alice, confirmed=True)
        assert await store.query(principal_id="alice", subject="a") == []
        assert (await store.query(principal_id="bob", subject="a"))[0]["fact_id"] == bob
        assert await SQLiteGraphStore(path).query(principal_id="alice", subject="a") == []
    asyncio.run(scenario())


def test_concurrent_erase_is_exactly_once(tmp_path):
    async def scenario():
        store = SQLiteGraphStore(tmp_path / "graph.sqlite")
        fid = await store.insert(principal_id="owner", subject="s", predicate="p", object="o")
        results = await asyncio.gather(*[
            store.delete_fact(principal_id="owner", fact_id=fid, confirmed=True)
            for _ in range(8)
        ])
        assert results.count(True) == 1 and results.count(False) == 7
    asyncio.run(scenario())


@pytest.mark.parametrize("principal,fact_id", [
    ("", "abc"), ("owner", ""), (" ", "abc"), ("owner", " "),
])
def test_bad_scopes_rejected(tmp_path, principal, fact_id):
    async def scenario():
        store = SQLiteGraphStore(tmp_path / "graph.sqlite")
        with pytest.raises(ValueError):
            await store.delete_fact(principal_id=principal, fact_id=fact_id, confirmed=True)
    asyncio.run(scenario())


def test_postgres_stays_fail_closed_without_database_call():
    class NoDB:
        def begin(self):
            raise AssertionError("database must not be contacted")
    store = PostgreSQLGraphStore("postgresql+asyncpg://host/db", engine=NoDB())
    async def scenario():
        with pytest.raises(PermissionError):
            await store.delete_fact(principal_id="owner", fact_id="id")
        with pytest.raises(ValueError):
            await store.delete_fact(principal_id="", fact_id="id", confirmed=True)
    asyncio.run(scenario())
