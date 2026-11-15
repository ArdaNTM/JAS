"""Offline academic metadata reconciliation and safe bibliography regressions."""
import pytest

from aura_core.research.citations import (
    AcademicMetadata,
    reconcile_academic_metadata,
    render_bibliography,
)


def record(source, title="A Paper", doi="10.1234/Example.1"):
    return AcademicMetadata(
        source_id=source, doi=doi, title=title, authors=("Doe, Jane",),
        publication_year=2026, venue="Journal",
    )


def test_same_doi_corroboration_is_not_claimed_as_verified():
    rows = [record("archive"), record("publisher")]
    result = reconcile_academic_metadata(rows)
    assert len(result) == 1
    assert result[0].source_ids == ("archive", "publisher")
    assert result[0].metadata_verified is False
    assert result[0].untrusted is True
    assert result[0].conflicting_metadata is False
    assert reconcile_academic_metadata(list(reversed(rows))) == result


def test_conflicting_metadata_never_silently_overwritten():
    conflicting = reconcile_academic_metadata(
        [record("archive"), record("publisher", title="Different Title")]
    )
    assert conflicting[0].conflicting_metadata
    assert "METADATA CONFLICT: REVIEW" in render_bibliography(conflicting)


def test_bibliography_escapes_untrusted_markup():
    malicious = record("archive", title="[Danger](javascript:alert(1))")
    line = render_bibliography(reconcile_academic_metadata([malicious]))
    assert r"\[Danger\]" in line
    assert "[Danger](" not in line


def test_duplicate_source_with_different_claims_rejected():
    with pytest.raises(ValueError, match="conflicting metadata"):
        reconcile_academic_metadata(
            [record("archive"), record("archive", title="Other")]
        )


@pytest.mark.parametrize("invalid", [
    record("src/private"),
    record("source", doi="https://127.0.0.1/secret"),
    record("source", doi="10.1234/evil{injection}"),
    record("source", title="multiline\ninjection"),
    AcademicMetadata("source", "10.1234/test", "x", (), 2026, "Journal"),
    AcademicMetadata("source", "10.1234/test", "x", ("Doe",), True, "Journal"),
])
def test_invalid_source_or_citation_fields_rejected(invalid):
    with pytest.raises(ValueError):
        reconcile_academic_metadata([invalid])


def test_limits_and_type_confusion_rejected():
    with pytest.raises(ValueError):
        reconcile_academic_metadata([record("archive")], max_dois=True)
    with pytest.raises(ValueError):
        reconcile_academic_metadata(
            [record(str(i), doi=f"10.1234/item{i}") for i in range(51)]
        )
    with pytest.raises(ValueError):
        render_bibliography(["unreviewed"])
