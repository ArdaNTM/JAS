from __future__ import annotations

import asyncio
from threading import Barrier

from aura_core.application.async_work import AsyncWorkCoordinator
from aura_core.application.context_synthesizer import ContextSynthesizer
from aura_core.application.predictive_simulation import PredictiveSimulator
from aura_core.application.system_telemetry import SystemTelemetry


def test_context_synthesizer_bounds_memory_and_keeps_evidence_as_data() -> None:
    result = ContextSynthesizer(max_memory_chars=256).synthesize(
        message="Özetle.",
        memories=["Kullanıcı Türkçe tercih ediyor." * 20],
        research_context='{"summary":"verified"}',
        tone="light",
    )
    assert result.recalled_items == 1
    assert len(result.user_content) < 15000
    assert "untrusted reference data" in result.system_prompt
    assert "light" == result.style


def test_simulator_reports_risk_without_executing_tools() -> None:
    class Risk:
        value = "high"

    class Step:
        step_id = "send"
        risk_level = Risk()
        arguments = {"destination": "external"}
        depends_on = set()

    result = PredictiveSimulator().simulate([Step()])
    assert result["recommendation"] == "review_before_execution"
    assert result["high_risk_steps"] == 1
    assert result["predicted_side_effecting_steps"] == 1
    assert result["findings"][0]["code"] == "high_risk_operation"


def test_simulator_blocks_missing_dependencies() -> None:
    class Step:
        step_id = "second"
        risk_level = "low"
        arguments = {}
        depends_on = {"missing"}

    result = PredictiveSimulator().simulate([Step()])
    assert result["recommendation"] == "do_not_execute"
    assert result["blockers"] == 1


def test_telemetry_handles_optional_dependency_missing(monkeypatch) -> None:
    # The collector degrades gracefully when psutil is not installed.
    telemetry = SystemTelemetry()
    result = telemetry.snapshot()
    assert result["status"] in {"ok", "unavailable"}
    assert "sampled_at" in result
    assert "alerts" in result


def test_async_coordinator_offloads_blocking_work_and_tracks_stats() -> None:
    async def scenario() -> None:
        coordinator = AsyncWorkCoordinator(capacity=2)
        barrier = Barrier(2)
        def operation(value: str) -> str:
            barrier.wait(timeout=2)
            return value

        results = await asyncio.gather(
            coordinator.run(lambda: operation("a")),
            coordinator.run(lambda: operation("b")),
        )
        assert results == ["a", "b"]
        snapshot = await coordinator.snapshot()
        assert snapshot.active == 0
        assert snapshot.completed == 2
        assert snapshot.failed == 0

    asyncio.run(scenario())



def test_async_coordinator_reduces_capacity_under_resource_pressure() -> None:
    async def scenario() -> None:
        coordinator = AsyncWorkCoordinator(capacity=3)
        await coordinator.apply_resource_pressure(True)
        assert (await coordinator.snapshot()).capacity == 1
        await coordinator.apply_resource_pressure(False)
        assert (await coordinator.snapshot()).capacity == 3

    asyncio.run(scenario())
