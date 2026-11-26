"""Astral HUD contracts: actual planner, bounded task events and launcher opt-ins."""
from pathlib import Path

from aura_core.application.directive_planner import DirectivePlanner
from aura_core.application.live_api import project_task_event

ROOT = Path(__file__).resolve().parents[2]


def test_porsche_visualization_and_research_are_separate_contracts():
    planner = DirectivePlanner()
    visual = planner.plan("Porsche 911'in motorunu göster")
    assert visual.resource_scope == "local-ui"
    assert len(visual.steps) == 1
    assert visual.steps[0].capability_id == "3d.visualize"
    assert visual.steps[0].arguments["model_id"] == "motor-v1"
    research = planner.plan("Araştır: Porsche 911'in motorunu")
    assert research.resource_scope == "public-web"
    assert [step.capability_id for step in research.steps] == ["internet.search"]
    matrix = planner.plan("AURA çekirdek matrisini yansıt")
    assert matrix.resource_scope == "local-ui"


def test_owned_task_projection_omits_provider_payload_and_other_tasks():
    event = {
        "id": "event-id", "event": "PlanStepCompleted",
        "source": "agent_executor", "timestamp": "2026-11-26T12:00:00Z",
        "data": {"task_id": "task-a", "step_id": "research-search",
                 "state": "succeeded", "attempts": 1, "result": "private data",
                 "arguments": {"secret": "private"}},
        "metadata": {"request_id": "private"},
    }
    assert project_task_event(event, "task-b") is None
    assert project_task_event({**event, "event": "SpeechAudioReady"}, "task-a") is None
    assert project_task_event({**event, "source": "external_provider"}, "task-a") is None
    projected = project_task_event(event, "task-a")
    assert projected == {
        "id": "event-id", "event": "PlanStepCompleted", "source": "agent_executor",
        "timestamp": "2026-11-26T12:00:00Z", "task_id": "task-a",
        "data": {"task_id": "task-a", "step_id": "research-search",
                 "state": "succeeded", "attempts": 1},
    }


def test_launcher_preserves_all_seven_explicit_user_opt_ins():
    source = (ROOT / "scripts/launch-aura-desktop.ps1").read_text(encoding="utf-8-sig")
    start = source.index("# Explicit per-user opt-ins")
    end = source.index("if ([string]::IsNullOrWhiteSpace($env:OLLAMA_MODELS))", start)
    block = source[start:end]
    for name in (
        "AURA_BACKGROUND_THINKING_ENABLED", "AURA_EVOLUTION_REVIEW_ENABLED",
        "AURA_EVOLUTION_INTROSPECTION_ENABLED", "AURA_EVOLUTION_SELF_PATCH_ENABLED",
        "AURA_EVOLUTION_SELF_PATCH_REVIEW_DIR", "AURA_JAS_ROOT", "AURA_EVOLUTION_MODEL",
    ):
        assert f'"{name}"' in block
    assert 'GetEnvironmentVariable($name, "User")' in block
    assert 'SetEnvironmentVariable($name, $userValue, "Process")' in block
    assert 'if ([string]::IsNullOrWhiteSpace($env:AURA_EVOLUTION_REVIEW_ENABLED))' in source
    assert 'if ([string]::IsNullOrWhiteSpace($env:AURA_BACKGROUND_THINKING_ENABLED))' in source


def test_hud_uses_real_task_and_read_only_review_contracts():
    ui = ROOT / "aura-ui/src"
    app = (ui / "App.tsx").read_text(encoding="utf-8")
    bridge = (ui / "AuraJarvisBridge.tsx").read_text(encoding="utf-8")
    drawer = (ui / "components/SystemDrawer.tsx").read_text(encoding="utf-8")
    assert "await generateTaskPlan" in app and "await createTask" in app
    assert "await getTask(submitted.task_id)" in app
    assert 'principal_id: "local_owner"' in app
    assert "generated.resource_scope" in app
    assert "invokeCapabilityTool" not in app
    assert "respondAsAssistant(" in bridge
    assert "speechChunks(result.assistant_reply" in bridge
    assert "LLM OFFLINE / DEGRADED" in bridge
    assert "getSelfPatches()" in drawer and "getPendingApprovals()" in drawer
    assert "/decision" not in drawer and "/resolve" not in drawer
    assert "localhost:8766" in drawer
