from __future__ import annotations

from types import SimpleNamespace

import pytest

from aura_core.application.persona_policy import PersonaPolicy, persona_from_mapping
from aura_core.application.reflexion_inference import ModelBackedDraftRevision, ModelRevisionConfig
from aura_core.application.background_thinking import propose_memory_consolidation


class FakeInference:
    def __init__(self, content: str):
        self.content = content
        self.requests = []

    def infer(self, request):
        self.requests.append(request)
        return SimpleNamespace(content=self.content, model="test-provider")


def test_model_revision_uses_provider_neutral_inference_and_bounds_output():
    inference = FakeInference("print(6 * 7)")
    revise = ModelBackedDraftRevision(
        inference=inference,
        config=ModelRevisionConfig(model="test-model", max_tokens=100),
    )
    assert revise("print(missing)", "NameError: missing (untrusted)", 1) == "print(6 * 7)"
    request = inference.requests[0]
    assert request.model == "test-model"
    assert request.temperature == 0
    assert "untrusted data" in request.messages[0].content
    assert "NameError" in request.messages[1].content
    assert "no tools" in request.messages[0].content


def test_model_revision_rejects_markdown_fences_and_oversized_output():
    fenced = ModelBackedDraftRevision(
        inference=FakeInference("```python\nprint(1)\n```"),
        config=ModelRevisionConfig(model="test-model"),
    )
    with pytest.raises(ValueError, match="fenced"):
        fenced("print(0)", "SyntaxError", 1)

    with pytest.raises(ValueError, match="max_source_chars"):
        ModelRevisionConfig(model="x", max_source_chars=64_001)


def test_persona_style_never_grants_initiative_without_opt_in_and_authorization():
    policy = PersonaPolicy(
        tone="dry_sarcastic",
        humor_intensity=2,
        initiative_enabled=True,
        initiative_threshold=3,
        daily_suggestion_budget=2,
        quiet_hours_start=22,
        quiet_hours_end=8,
    )
    prompt = policy.system_style_prompt()
    assert "Permission Engine" in prompt
    assert "MCP Gateway" in prompt
    assert policy.may_suggest_initiative(
        signal_strength=4, local_hour=14, suggestions_today=0,
        user_opted_in=True, action_is_authorized=True,
    )
    assert not policy.may_suggest_initiative(
        signal_strength=4, local_hour=14, suggestions_today=0,
        user_opted_in=False, action_is_authorized=True,
    )
    assert not policy.may_suggest_initiative(
        signal_strength=4, local_hour=14, suggestions_today=0,
        user_opted_in=True, action_is_authorized=False,
    )
    assert not policy.may_suggest_initiative(
        signal_strength=4, local_hour=23, suggestions_today=0,
        user_opted_in=True, action_is_authorized=True,
    )
    assert not policy.may_suggest_initiative(
        signal_strength=4, local_hour=14, suggestions_today=2,
        user_opted_in=True, action_is_authorized=True,
    )


def test_persona_rejects_unknown_fields():
    with pytest.raises(ValueError, match="unsupported persona settings"):
        persona_from_mapping({"initiative_enabled": True, "grant_admin": True})


def test_memory_consolidation_produces_reviewable_provenanced_candidates():
    records = [
        SimpleNamespace(memory_id="m1", content="sandbox python timeout error retry policy"),
        SimpleNamespace(memory_id="m2", content="sandbox python timeout error retry improved"),
        SimpleNamespace(memory_id="m3", content="sandbox python timeout error retry fixed"),
    ]
    proposals = propose_memory_consolidation(records, max_proposals=5)
    assert proposals
    assert all(item["review_required"] for item in proposals)
    assert all(item["untrusted"] for item in proposals)
    assert all(len(item["evidence_memory_ids"]) == 2 for item in proposals)
    assert all(item["execution_performed"] is False for item in proposals)
    assert any(item["kind"] == "possible_repeated_lesson" for item in proposals)


def test_memory_consolidation_flags_possible_contradictions_without_resolving_them():
    records = [
        SimpleNamespace(memory_id="m1", content="cache always enabled improves latency stability"),
        SimpleNamespace(memory_id="m2", content="cache never enabled improves latency stability"),
    ]
    proposals = propose_memory_consolidation(records)
    assert any(item["kind"] == "possible_memory_contradiction" for item in proposals)
    assert all(item["review_required"] for item in proposals)
