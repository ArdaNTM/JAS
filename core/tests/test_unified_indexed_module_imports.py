"""Structural compatibility smoke for indexed standalone sources.

This test deliberately imports real modules rather than faking external engines.
It is necessary but *not sufficient* for feature acceptance.
"""
from __future__ import annotations
import importlib
import pytest

MODULES = (
    "aura_core.memory.conversation_review",
    "aura_core.application.goal_planning",
    "aura_core.research.scientific_journal",
    "aura_core.tts.kokoro_guard",
    "aura_core.application.text_change_preview",
    "aura_core.research.evidence",
    "aura_core.research.citations",
    "aura_core.filesystem.docx_extractor",
    "aura_core.research.feed_monitor",
    "aura_core.research.archive",
    "aura_core.application.offline_code_quality",
    "aura_core.application.code_insight",
    "aura_core.telemetry.runtime_summary",
    "aura_core.application.specialist_selection",
    "aura_core.application.agent_mailbox",
    "aura_core.application.specialist_performance",
    "aura_core.application.experiment_design",
    "aura_core.research.scientific_triage",
    "aura_core.science.analysis",
    "aura_core.science.linear_model",
    "aura_core.application.physics_simulation",
    "aura_core.application.parametric_mesh",
    "aura_core.application.action_history",
    "aura_core.persistence.offline_backup",
    "aura_core.enterprise.audit_checkpoint",
    "aura_core.application.offline_email",
    "aura_core.application.ics_calendar",
    "aura_core.filesystem.media_header",
    "aura_core.data_analysis.tabular",
    "aura_core.application.offline_xlsx_report",
    "aura_core.application.language_learning",
    "aura_core.application.subsystem_pack1",
    "aura_core.application.subsystem_pack2",
    "aura_core.application.subsystem_pack3",
    "aura_core.application.hud_game_blueprint",
    "aura_core.memory.episodic_mcp",
)

@pytest.mark.parametrize("module", MODULES)
def test_offline_module_imports_without_side_effects(module):
    loaded = importlib.import_module(module)
    assert loaded.__name__ == module
