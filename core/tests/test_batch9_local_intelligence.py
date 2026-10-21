from __future__ import annotations

import asyncio
import math

import pytest

from aura_core.application.predictive_prefetch import PredictivePrefetchPlanner
from aura_core.application.self_tool_synthesis import CandidateToolValidator, ToolCandidate
from aura_core.memory.local_vector_store import LocalVectorMemory
from aura_core.providers.local_vision import LocalOllamaVisionProvider, _validate_local_endpoint


class TinyEmbedder:
    model = "test-local"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            lowered = text.casefold()
            vectors.append([
                float(sum(word in lowered for word in ("weather", "rain", "forecast"))),
                float(sum(word in lowered for word in ("cpu", "memory", "system"))),
                float(sum(word in lowered for word in ("turkish", "language", "short"))),
            ])
        return vectors


def test_local_vector_memory_uses_cosine_ranking_and_principal_scope(tmp_path) -> None:
    store = LocalVectorMemory(tmp_path / "vectors.sqlite3", TinyEmbedder())
    asyncio.run(store.remember(principal_id="alice", content="weather forecast rain"))
    asyncio.run(store.remember(principal_id="alice", content="system CPU memory"))
    asyncio.run(store.remember(principal_id="bob", content="weather forecast rain"))

    result = asyncio.run(store.recall(principal_id="alice", query="rain forecast weather"))
    assert len(result) == 2
    assert result[0]["score"] == pytest.approx(1.0)
    assert all(item["principal_id"] == "alice" for item in result)
    assert asyncio.run(store.recall(principal_id="bob", query="CPU memory system"))[0]["principal_id"] == "bob"


def test_candidate_tool_is_review_only_and_dangerous_constructs_rejected() -> None:
    validator = CandidateToolValidator()
    safe = ToolCandidate(
        tool_name="normalize_text",
        description="Normalize input text.",
        source_code="def run(data):\n    return {\"text\": str(data.get(\"text\", \"\")).strip().lower()}\n",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    proposal = validator.create_proposal(safe)
    assert proposal["validation"]["valid"] is True
    assert proposal["manifest"]["execution_enabled"] is False
    assert proposal["validation"]["sandbox_execution"] == "not_performed"

    unsafe = ToolCandidate(
        tool_name="run_shell",
        description="Execute shell.",
        source_code="import subprocess\ndef run(data):\n    return subprocess.run(data)\n",
        input_schema={},
        output_schema={},
    )
    rejected = validator.validate(unsafe)
    assert rejected["valid"] is False
    assert any("import not allow-listed" in error for error in rejected["errors"])


def test_prefetch_requires_repeated_local_patterns_and_never_executes(tmp_path) -> None:
    planner = PredictivePrefetchPlanner(tmp_path / "prefetch.sqlite3", min_observations=3)
    assert planner.observe(principal_id="alice", event_key="morning_start", capability_id="weather.read", hour_local=7) is None
    assert planner.observe(principal_id="alice", event_key="morning_start", capability_id="weather.read", hour_local=7) is None
    proposal = planner.observe(principal_id="alice", event_key="morning_start", capability_id="weather.read", hour_local=7)
    assert proposal is not None
    assert proposal["status"] == "pending_approval"
    assert proposal["execution"] == "not_performed"
    assert len(planner.proposals(principal_id="alice")) == 1
    assert planner.proposals(principal_id="bob") == []


def test_vision_provider_rejects_nonlocal_endpoints() -> None:
    with pytest.raises(ValueError, match="cloud and non-loopback"):
        _validate_local_endpoint("https://api.example.com")
    with pytest.raises(ValueError, match="cloud and non-loopback"):
        LocalOllamaVisionProvider(base_url="http://192.0.2.10:11434")
    provider = LocalOllamaVisionProvider(base_url="http://127.0.0.1:11434")
    assert provider.model == "qwen2.5vl:3b"


def test_prefetch_kernel_event_requires_explicit_capability_and_local_hour(tmp_path) -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace

    planner = PredictivePrefetchPlanner(tmp_path / "event-prefetch.sqlite3", min_observations=2)
    missing = SimpleNamespace(event_type="TaskCompleted", payload={"principal_id": "alice"}, timestamp=datetime.now(UTC))
    assert planner.observe_kernel_event(missing) is None
    event = SimpleNamespace(
        event_type="MorningRoutine",
        payload={"principal_id": "alice", "prefetch_capability_id": "weather.read", "local_hour": 7},
        timestamp=datetime.now(UTC),
    )
    assert planner.observe_kernel_event(event) is None
    proposal = planner.observe_kernel_event(event)
    assert proposal is not None
    assert proposal["status"] == "pending_approval"
