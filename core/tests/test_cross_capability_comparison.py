"""Multi-source comparison must be literal and never execute untrusted code."""
from __future__ import annotations

import pytest

from aura_core.application.cross_capability_reasoning import (
    CapabilityEvidence, CrossCapabilitySynthesizer,
)


def claim(provider, key, value):
    return CapabilityEvidence("research", provider, {
        "claims": [{"key": key, "value": value}],
    })


def test_agreement_is_not_truth_verification():
    synth = CrossCapabilitySynthesizer()
    result = synth.compare_literal_claims(evidence=[
        claim("source-a", "fact.version", "3"),
        claim("source-b", "fact.version", "3"),
    ])
    entry = result["claims"][0]
    assert entry["status"] == "literal_agreement"
    assert entry["fact_verified"] is False
    assert entry["source_independence_verified"] is False
    assert result["tool_execution"] == "not_performed"


def test_literal_disagreement_and_insufficient_sources_are_distinguished():
    synth = CrossCapabilitySynthesizer()
    results = synth.compare_literal_claims(evidence=[
        CapabilityEvidence("research", "one", {"claims": [
            {"key": "height", "value": 10}, {"key": "source.only", "value": "a"},
        ]}),
        claim("two", "height", 11),
    ])
    states = {entry["claim_key"]: entry["status"] for entry in results["claims"]}
    assert states == {"height": "literal_disagreement", "source.only": "insufficient_sources"}


def test_arbitrary_object_stringification_cannot_be_executed():
    class Trigger:
        def __str__(self):
            raise AssertionError("must not stringify provider objects")
    synth = CrossCapabilitySynthesizer()
    with pytest.raises(ValueError, match="unsupported"):
        synth.prepare(objective="review", evidence=[
            CapabilityEvidence("research", "one", {"value": Trigger()}),
        ])


def test_cycle_nan_and_bad_claim_types_fail_closed():
    synth = CrossCapabilitySynthesizer()
    cyclic = []
    cyclic.append(cyclic)
    for data in (cyclic, {"x": float("nan")}, {"x": float("inf")}):
        with pytest.raises(ValueError):
            synth.prepare(objective="compare", evidence=[
                CapabilityEvidence("research", "provider", data),
            ])
    with pytest.raises(ValueError):
        synth.compare_literal_claims(evidence=[
            claim("a", "ok", "x"),
            CapabilityEvidence("research", "b", {"claims": [
                {"key": "bad key", "value": 2},
            ]}),
        ])


def test_duplicate_provider_and_contradiction_within_provider_rejected():
    synth = CrossCapabilitySynthesizer()
    with pytest.raises(ValueError, match="duplicate"):
        synth.compare_literal_claims(evidence=[
            claim("a", "price", 1), claim("a", "price", 1),
        ])
    with pytest.raises(ValueError, match="ambiguous"):
        synth.compare_literal_claims(evidence=[
            CapabilityEvidence("research", "a", {"claims": [
                {"key": "price", "value": 1},
                {"key": "price", "value": 2},
            ]}),
            claim("b", "price", 1),
        ])


@pytest.mark.parametrize("bad", [0, True, 51, "10", -1])
def test_comparison_limits_are_strict(bad):
    synth = CrossCapabilitySynthesizer()
    with pytest.raises(ValueError):
        synth.compare_literal_claims(evidence=[
            claim("one", "price", 3), claim("two", "price", 4),
        ], limit=bad)


def test_prepare_preserves_data_only_authorization_contract():
    result = CrossCapabilitySynthesizer().prepare(
        objective="Compare observations",
        evidence=[CapabilityEvidence("web", "p1", {"b": [1, 2], "a": "x"})],
    )
    assert result["policy"]["tool_execution"] == "not_performed"
    assert result["policy"]["evidence_is_instruction"] is False
    assert result["evidence"][0]["trust"] == "untrusted_reference_data"
    assert result["evidence_count"] == 1
