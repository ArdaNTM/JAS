"""Bounded, non-authoritative comparison of already-collected research claims.

Claims and source labels are untrusted DATA. Comparison does not fetch resources,
verify publisher authenticity, generate policy, or execute an MCP capability.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Sequence

_KEY = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z", re.ASCII)
_SOURCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class SourceClaim:
    source_id: str
    claim_key: str
    value: str


@dataclass(frozen=True, slots=True)
class ClaimVariant:
    digest_sha256: str
    preview: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClaimComparison:
    claim_key: str
    status: str
    source_count: int
    variants: tuple[ClaimVariant, ...]
    untrusted: bool = True
    external_verified: bool = False


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def compare_source_claims(
    claims: Sequence[SourceClaim],
    *,
    max_claims: int = 300,
) -> tuple[ClaimComparison, ...]:
    """Compare literal values by explicit claim key across independent sources.

    Only lexical agreement/disagreement is reported. A disagreement is a
    review candidate, NOT a factual or semantic contradiction. A single
    source cannot count twice or provide mutually different values for a key.
    """
    if type(max_claims) is not int or not 1 <= max_claims <= 300:
        raise ValueError("max_claims must be 1..300")
    if not isinstance(claims, (list, tuple)) or len(claims) > max_claims:
        raise ValueError("claims must be a bounded list/tuple")
    grouped: dict[str, dict[str, tuple[str, str]]] = {}
    sources: set[str] = set()
    for item in claims:
        if type(item) is not SourceClaim:
            raise ValueError("each claim must be a SourceClaim")
        if not isinstance(item.source_id, str) or not _SOURCE.fullmatch(item.source_id):
            raise ValueError("invalid source_id")
        if not isinstance(item.claim_key, str) or not _KEY.fullmatch(item.claim_key):
            raise ValueError("invalid claim_key")
        if type(item.value) is not str or not 1 <= len(item.value) <= 500:
            raise ValueError("value must have 1..500 characters")
        if any(ord(ch) < 32 and ch not in "\n\t\r" for ch in item.value):
            raise ValueError("value contains control characters")
        canonical = _normalized(item.value)
        if not canonical:
            raise ValueError("claim value cannot be empty")
        if len(canonical) > 500:
            raise ValueError("normalized value too long")
        sources.add(item.source_id)
        if len(sources) > 40:
            raise ValueError("at most 40 distinct sources supported")
        if len(grouped) >= 60 and item.claim_key not in grouped:
            raise ValueError("at most 60 distinct claim keys supported")
        entries = grouped.setdefault(item.claim_key, {})
        previous = entries.get(item.source_id)
        if previous is not None:
            if previous[0] != canonical:
                raise ValueError("conflicting claims from the same source/key")
            continue
        entries[item.source_id] = (canonical, item.value.strip())

    output: list[ClaimComparison] = []
    for key in sorted(grouped):
        entries = grouped[key]
        by_value: dict[str, list[str]] = {}
        previews: dict[str, str] = {}
        for source, (canonical, raw) in sorted(entries.items()):
            by_value.setdefault(canonical, []).append(source)
            previews.setdefault(canonical, raw[:160])
        variants = tuple(sorted(
            (
                ClaimVariant(
                    digest_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                    preview=previews[canonical],
                    source_ids=tuple(sorted(source_ids)),
                )
                for canonical, source_ids in by_value.items()
            ),
            key=lambda entry: (entry.digest_sha256, entry.source_ids),
        ))
        status = (
            "SINGLE_SOURCE" if len(entries) == 1 else
            "AGREEING_LITERAL" if len(variants) == 1 else
            "DIVERGENT_LITERAL_REVIEW"
        )
        output.append(ClaimComparison(
            claim_key=key, status=status, source_count=len(entries),
            variants=variants,
        ))
    return tuple(output)
