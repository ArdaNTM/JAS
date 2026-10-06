from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class AdmissionDecision(StrEnum):
    ACCEPT = "accept"
    DUPLICATE = "duplicate"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    decision: AdmissionDecision
    content_hash: str
    reason: str


class AdmissionController:
    """
    Deterministic first-stage admission controller.

    This stage performs exact normalized-content duplicate detection.
    Semantic novelty is intentionally deferred to the semantic-memory
    layer so this controller remains deterministic and inexpensive.
    """

    def __init__(
        self,
        existing_hashes: Iterable[str] | None = None,
        *,
        min_content_length: int = 1,
    ) -> None:
        if min_content_length < 1:
            raise ValueError(
                "min_content_length must be positive"
            )

        self._hashes: set[str] = set(
            existing_hashes or ()
        )
        self._min_content_length = min_content_length

    @staticmethod
    def normalize(content: str) -> str:
        return " ".join(content.split()).casefold()

    @classmethod
    def content_hash(cls, content: str) -> str:
        normalized = cls.normalize(content)

        return hashlib.sha256(
            normalized.encode("utf-8")
        ).hexdigest()

    def evaluate(
        self,
        content: str,
    ) -> AdmissionResult:
        if not isinstance(content, str):
            return AdmissionResult(
                decision=AdmissionDecision.REJECT,
                content_hash="",
                reason="Content must be a string",
            )

        normalized = self.normalize(content)

        if len(normalized) < self._min_content_length:
            return AdmissionResult(
                decision=AdmissionDecision.REJECT,
                content_hash="",
                reason=(
                    "Content is empty or below minimum length"
                ),
            )

        digest = self.content_hash(normalized)

        if digest in self._hashes:
            return AdmissionResult(
                decision=AdmissionDecision.DUPLICATE,
                content_hash=digest,
                reason=(
                    "Exact normalized content already admitted"
                ),
            )

        return AdmissionResult(
            decision=AdmissionDecision.ACCEPT,
            content_hash=digest,
            reason=(
                "Content passed deterministic admission checks"
            ),
        )

    def commit(
        self,
        result: AdmissionResult,
    ) -> None:
        if result.decision is not AdmissionDecision.ACCEPT:
            raise ValueError(
                "Only accepted content can be committed"
            )

        self._hashes.add(result.content_hash)

    def admit(
        self,
        content: str,
    ) -> AdmissionResult:
        result = self.evaluate(content)

        if result.decision is AdmissionDecision.ACCEPT:
            self.commit(result)

        return result

    def __len__(self) -> int:
        return len(self._hashes)
