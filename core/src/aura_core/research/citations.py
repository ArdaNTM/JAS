"""Offline citation metadata reconciliation, never publisher verification.

Inputs must already have passed an authorized research retrieval boundary.
No network, model calls, file IO, or provider dispatch is permitted here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

SOURCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}\Z", re.ASCII)
DOI = re.compile(r"10\.[0-9]{4,9}/[A-Za-z0-9._;()/:+-]{1,160}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class AcademicMetadata:
    source_id: str
    doi: str
    title: str
    authors: tuple[str, ...]
    publication_year: int
    venue: str


@dataclass(frozen=True, slots=True)
class CitationReview:
    doi: str
    title: str
    authors: tuple[str, ...]
    publication_year: int
    venue: str
    source_ids: tuple[str, ...]
    conflicting_metadata: bool
    metadata_verified: bool = False
    untrusted: bool = True


def _valid_text(value: object, max_chars: int) -> bool:
    return (
        type(value) is str and bool(value.strip())
        and len(value) <= max_chars
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def reconcile_academic_metadata(
    records: Sequence[AcademicMetadata], *, max_dois: int = 50
) -> tuple[CitationReview, ...]:
    """Deduplicate by DOI; conflicting descriptions remain marked for review."""
    if type(max_dois) is not int or not 1 <= max_dois <= 50:
        raise ValueError("max_dois must be 1..50")
    if not isinstance(records, (list, tuple)) or len(records) > 150:
        raise ValueError("at most 150 citation observations allowed")
    grouped: dict[str, dict[str, AcademicMetadata]] = {}
    for row in records:
        if type(row) is not AcademicMetadata:
            raise ValueError("AcademicMetadata record required")
        if (
            type(row.source_id) is not str or not SOURCE.fullmatch(row.source_id)
            or type(row.doi) is not str or not DOI.fullmatch(row.doi.strip())
            or not _valid_text(row.title, 300)
            or not _valid_text(row.venue, 160)
            or type(row.authors) is not tuple
            or not 1 <= len(row.authors) <= 20
            or not all(_valid_text(author, 120) for author in row.authors)
            or type(row.publication_year) is not int
            or not 1000 <= row.publication_year <= 2200
        ):
            raise ValueError("invalid academic citation fields")
        doi = row.doi.strip().casefold()
        entries = grouped.setdefault(doi, {})
        if len(grouped) > max_dois:
            raise ValueError("DOI limit exceeded")
        previous = entries.get(row.source_id)
        if previous is not None and previous != row:
            raise ValueError("conflicting metadata from same source")
        entries[row.source_id] = row
    reviews: list[CitationReview] = []
    for doi, entries in sorted(grouped.items()):
        variants = {
            (
                record.title.strip().casefold(),
                tuple(author.strip().casefold() for author in record.authors),
                record.publication_year, record.venue.strip().casefold(),
            )
            for record in entries.values()
        }
        selected = entries[min(entries)]
        reviews.append(CitationReview(
            doi=doi, title=selected.title.strip(),
            authors=tuple(author.strip() for author in selected.authors),
            publication_year=selected.publication_year,
            venue=selected.venue.strip(), source_ids=tuple(sorted(entries)),
            conflicting_metadata=len(variants) > 1,
        ))
    return tuple(reviews)


def _escape_markdown(value: str) -> str:
    special = set("\\*_{}[]()#+.!>|-") | {chr(96)}
    return "".join("\\" + c if c in special else c for c in value)


def render_bibliography(reviews: Sequence[CitationReview]) -> str:
    """Render readable citations as escaped text, not live source links."""
    if not isinstance(reviews, (list, tuple)) or len(reviews) > 50:
        raise ValueError("bounded CitationReview sequence required")
    if any(type(item) is not CitationReview for item in reviews):
        raise ValueError("CitationReview entries required")
    lines = []
    for review in sorted(reviews, key=lambda entry: entry.doi):
        authors = ", ".join(_escape_markdown(name) for name in review.authors)
        title = _escape_markdown(review.title)
        venue = _escape_markdown(review.venue)
        doi = _escape_markdown(review.doi)
        suffix = " [METADATA CONFLICT: REVIEW]" if review.conflicting_metadata else ""
        lines.append(
            f"- {authors} ({review.publication_year}). {title}. {venue}. DOI: {doi}.{suffix}"
        )
    return "\n".join(lines)
