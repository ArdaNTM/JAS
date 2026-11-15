"""Offline bounded scientific metadata screening and materials-range comparison.

All study metadata, paper identities and material values are caller-provided
UNVERIFIED evidence. No literature retrieval, scientific certification,
web access, laboratory execution or MCP authority occurs.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

_DOI = re.compile(r"10\.[0-9]{4,9}/[a-z0-9._;()/:+-]{1,160}\Z", re.ASCII)
_ID = re.compile(r"[A-Za-z][A-Za-z0-9._-]{0,79}\Z", re.ASCII)
_PROPERTIES = frozenset({
    "density_kg_m3", "tensile_strength_mpa", "yield_strength_mpa",
    "elastic_modulus_gpa", "thermal_conductivity_w_mk",
})


@dataclass(frozen=True, slots=True)
class StudyMetadata:
    doi: str
    title: str
    abstract: str
    publication_year: int


@dataclass(frozen=True, slots=True)
class ScreenedStudy:
    doi: str
    included_by_literal_rules: bool
    exclusion_reasons: tuple[str, ...]
    metadata_sha256: str
    publisher_verified: bool = False
    untrusted: bool = True


@dataclass(frozen=True, slots=True)
class LiteratureScreening:
    results: tuple[ScreenedStudy, ...]
    included_count: int
    full_text_reviewed: bool = False
    scientific_quality_assessed: bool = False
    source_authorization_checked: bool = False


@dataclass(frozen=True, slots=True)
class MaterialPropertyRange:
    material_id: str
    property_code: str
    minimum: float
    maximum: float
    source_doi: str


@dataclass(frozen=True, slots=True)
class MaterialPairComparison:
    left_material: str
    right_material: str
    relation: str
    evidence_untrusted: bool = True


@dataclass(frozen=True, slots=True)
class MaterialEvidenceComparison:
    property_code: str
    preferred_direction: str
    pairs: tuple[MaterialPairComparison, ...]
    units_assumed: bool = True
    source_authenticity_verified: bool = False
    material_safety_verified: bool = False
    physical_testing_performed: bool = False
    recommendation_authorized: bool = False


def _doi(value: object) -> str:
    if type(value) is not str:
        raise ValueError("DOI must be string")
    normalized = value.casefold()
    if not _DOI.fullmatch(normalized):
        raise ValueError("invalid DOI identifier")
    return normalized


def _metadata(study: StudyMetadata) -> tuple[str, str, str, int]:
    if type(study) is not StudyMetadata:
        raise ValueError("StudyMetadata required")
    doi = _doi(study.doi)
    for value, cap in ((study.title, 300), (study.abstract, 4000)):
        if (
            type(value) is not str or not value.strip() or len(value) > cap
            or any(ord(char) in (0, 13) for char in value)
        ):
            raise ValueError("invalid bounded study metadata")
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("invalid study Unicode") from exc
    year = study.publication_year
    if type(year) is not int or not 1800 <= year <= 2100:
        raise ValueError("invalid publication year")
    return doi, study.title, study.abstract, year


def screen_studies(
    studies: tuple[StudyMetadata, ...], *,
    required_terms: tuple[str, ...],
    first_year: int = 2000, last_year: int = 2100,
) -> LiteratureScreening:
    """Apply explicit title/abstract literal eligibility, not paper quality."""
    if type(studies) is not tuple or not 1 <= len(studies) <= 100:
        raise ValueError("1..100 studies required")
    if (
        type(required_terms) is not tuple or not 1 <= len(required_terms) <= 8
        or any(
            type(term) is not str or not 2 <= len(term.strip()) <= 50
            or term != term.strip()
            or any(ord(ch) < 32 for ch in term)
            for term in required_terms
        )
    ):
        raise ValueError("1..8 bounded search terms required")
    if (
        type(first_year) is not int or type(last_year) is not int
        or not 1800 <= first_year <= last_year <= 2100
    ):
        raise ValueError("invalid screening year window")
    seen: set[str] = set()
    decisions: list[ScreenedStudy] = []
    total = 0
    terms = tuple(term.casefold() for term in required_terms)
    for study in studies:
        doi, title, abstract, year = _metadata(study)
        if doi in seen:
            raise ValueError("duplicate unverified study DOI")
        seen.add(doi)
        total += len(title.encode("utf-8")) + len(abstract.encode("utf-8"))
        if total > 400000:
            raise ValueError("study evidence budget exceeded")
        reasons: list[str] = []
        if not first_year <= year <= last_year:
            reasons.append("publication_year_outside_window")
        haystack = (title + " " + abstract).casefold()
        if not all(term in haystack for term in terms):
            reasons.append("required_literal_term_missing")
        fingerprint = hashlib.sha256(
            (doi + "\0" + title + "\0" + abstract + "\0" + str(year))
            .encode("utf-8")
        ).hexdigest()
        decisions.append(ScreenedStudy(
            doi=doi, included_by_literal_rules=not reasons,
            exclusion_reasons=tuple(reasons), metadata_sha256=fingerprint,
        ))
    decisions.sort(key=lambda result: result.doi)
    return LiteratureScreening(
        results=tuple(decisions),
        included_count=sum(result.included_by_literal_rules for result in decisions),
    )


def compare_material_ranges(
    claims: tuple[MaterialPropertyRange, ...],
    *, sources: tuple[StudyMetadata, ...], property_code: str,
    preferred_direction: str = "higher",
) -> MaterialEvidenceComparison:
    """Compare non-overlapping claimed ranges in an explicit named unit.

    Range separation is a mathematical observation, NOT certified material
    selection or statistical/scientific truth about the underlying studies.
    """
    if type(claims) is not tuple or not 2 <= len(claims) <= 20:
        raise ValueError("2..20 material claims required")
    if type(sources) is not tuple or not 1 <= len(sources) <= 100:
        raise ValueError("bounded source metadata tuple required")
    if type(property_code) is not str or property_code not in _PROPERTIES:
        raise ValueError("unsupported physical property units")
    if type(preferred_direction) is not str or preferred_direction not in {"higher", "lower"}:
        raise ValueError("preferred direction must be higher/lower")
    source_ids: set[str] = set()
    for source in sources:
        doi, _, _, _ = _metadata(source)
        if doi in source_ids:
            raise ValueError("duplicate source DOI")
        source_ids.add(doi)
    material_ids: set[str] = set()
    evaluated: list[MaterialPropertyRange] = []
    for claim in claims:
        if type(claim) is not MaterialPropertyRange:
            raise ValueError("MaterialPropertyRange required")
        identifier = claim.material_id
        if type(identifier) is not str or not _ID.fullmatch(identifier):
            raise ValueError("invalid material ID")
        if identifier.casefold() in material_ids:
            raise ValueError("duplicate material claim identity")
        material_ids.add(identifier.casefold())
        if claim.property_code != property_code:
            raise ValueError("incomparable material property or units")
        values = (claim.minimum, claim.maximum)
        if any(
            type(v) not in (int, float) or not math.isfinite(v)
            or not 0 <= v <= 1e9 for v in values
        ) or claim.minimum > claim.maximum:
            raise ValueError("invalid physical property claim range")
        if _doi(claim.source_doi) not in source_ids:
            raise ValueError("material property lacks supplied study provenance")
        evaluated.append(claim)
    evaluated.sort(key=lambda claim: claim.material_id.casefold())
    pairs: list[MaterialPairComparison] = []
    for i, left in enumerate(evaluated):
        for right in evaluated[i + 1:]:
            relation = "ranges_overlap_or_touch"
            if left.minimum > right.maximum:
                relation = "left_strictly_preferred" if preferred_direction == "higher" else "right_strictly_preferred"
            elif right.minimum > left.maximum:
                relation = "right_strictly_preferred" if preferred_direction == "higher" else "left_strictly_preferred"
            pairs.append(MaterialPairComparison(
                left.material_id, right.material_id, relation,
            ))
    return MaterialEvidenceComparison(
        property_code=property_code, preferred_direction=preferred_direction,
        pairs=tuple(pairs),
    )
