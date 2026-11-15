"""Feature #37: compare independent, explicitly keyed, untrusted evidence."""
from __future__ import annotations

import pytest

from aura_core.research.source_comparison import SourceClaim, compare_source_claims


def test_corresponding_claims_agree_and_diverge_without_claiming_truth():
    claims = [
        SourceClaim("source-1", "population.city", "One Million"),
        SourceClaim("source-2", "population.city", " one   million "),
        SourceClaim("source-2", "weather.city", "Sunny"),
        SourceClaim("source-3", "weather.city", "Rainy"),
        SourceClaim("source-1", "solo.fact", "One source"),
    ]
    got = {item.claim_key: item for item in compare_source_claims(claims)}
    assert got["population.city"].status == "AGREEING_LITERAL"
    assert got["population.city"].source_count == 2
    assert got["population.city"].variants[0].source_ids == ("source-1", "source-2")
    assert got["weather.city"].status == "DIVERGENT_LITERAL_REVIEW"
    assert len(got["weather.city"].variants) == 2
    assert got["weather.city"].untrusted is True
    assert got["weather.city"].external_verified is False
    assert got["solo.fact"].status == "SINGLE_SOURCE"


def test_same_source_never_counts_as_independent_corroboration():
    one = SourceClaim("source-1", "value", "A")
    result = compare_source_claims([one, one])
    assert result[0].source_count == 1
    assert result[0].status == "SINGLE_SOURCE"
    with pytest.raises(ValueError, match="conflicting claims"):
        compare_source_claims([one, SourceClaim("source-1", "value", "B")])


def test_deterministic_order_and_unicode_normalization():
    items = [
        SourceClaim("z", "zeta", "CAFÉ"),
        SourceClaim("a", "zeta", "cafe\u0301"),
        SourceClaim("a", "alpha", "Small"),
    ]
    assert compare_source_claims(items) == compare_source_claims(list(reversed(items)))
    results = compare_source_claims(items)
    assert [row.claim_key for row in results] == ["alpha", "zeta"]
    assert results[1].status == "AGREEING_LITERAL"


@pytest.mark.parametrize("items", [
    "not a list",
    [object()],
    [SourceClaim("x", "bad key", "value")],
    [SourceClaim("x/foo", "ok", "value")],
    [SourceClaim("x", "ok", "\x00")],
    [SourceClaim("x", "ok", " \t ")],
    [SourceClaim("x", "ok", "x" * 501)],
    [SourceClaim("x", "ok", "x")] * 301,
    [SourceClaim(str(i), "ok", "same") for i in range(41)],
    [SourceClaim("x", f"k{i}", "value") for i in range(61)],
])
def test_untrusted_input_fail_closed(items):
    with pytest.raises(ValueError):
        compare_source_claims(items)


def test_budget_invalid_bool_and_limits_rejected():
    with pytest.raises(ValueError):
        compare_source_claims([], max_claims=True)
    with pytest.raises(ValueError):
        compare_source_claims([], max_claims=0)
    assert compare_source_claims([]) == ()
