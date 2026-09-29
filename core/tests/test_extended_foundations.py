import asyncio
from pathlib import Path

from aura_core.memory.store import InMemoryStore, MemoryQuery, MemoryRecord
from aura_core.models.routing import ModelDefinition, ModelRegistry, ModelRequirements, ModelRouter
from aura_core.persistence.repository import InMemoryRepository, PersistedRecord
from aura_core.plugins.registry import PluginManifest, PluginRegistry
from aura_core.release.manifest import ReleaseManifest


def test_memory_is_namespace_and_metadata_aware() -> None:
    store = InMemoryStore()
    asyncio.run(store.put(MemoryRecord("1", "task", "Alpha result", "agent", {"kind": "result"})))
    asyncio.run(store.put(MemoryRecord("2", "other", "Alpha result", "agent")))
    found = asyncio.run(store.search(MemoryQuery("task", "alpha", {"kind": "result"})))
    assert [record.record_id for record in found] == ["1"]


def test_model_router_is_stable_and_provider_agnostic() -> None:
    registry = ModelRegistry()
    registry.register(ModelDefinition("z", "provider:z", frozenset({"chat"}), priority=1, quality=1, latency_ms=1, max_context_tokens=8))
    registry.register(ModelDefinition("a", "provider:a", frozenset({"chat"}), priority=1, quality=2, latency_ms=100, max_context_tokens=8))
    assert ModelRouter(registry).select(ModelRequirements(frozenset({"chat"}), 4)).model_id == "a"


def test_persistence_revision_plugin_and_release_digest() -> None:
    repository = InMemoryRepository()
    assert asyncio.run(repository.save(PersistedRecord("task", "1", {"state": "new"}))).revision == 1
    assert asyncio.run(repository.save(PersistedRecord("task", "1", {"state": "done"}))).revision == 2
    plugins = PluginRegistry()
    plugins.register(PluginManifest("sample", "1", frozenset({"sample.read"})))
    plugins.activate("sample")
    manifest = ReleaseManifest("0.1.0", {"core": "0.1.0"}, {"python": "3.13.14"})
    assert len(manifest.digest()) == 64
