"""Quarantined mutation review queue: no importlib, installation or live writes.

The model may propose candidate source as UNTRUSTED DATA. Only a fresh owner
approval can request a bounded smoke test through the pre-existing MCP Gateway.
A smoke test is NOT an independent attestation and NEVER activates a tool.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from aura_core.application.self_tool_synthesis import CandidateToolValidator, ToolCandidate
from aura_core.evolution.sandbox_review import GovernedSandboxReview, SandboxSmokeReport

_ID = re.compile(r"^[a-f0-9]{24}$")


@dataclass(frozen=True, slots=True)
class MutationDraft:
    draft_id: str
    finding_id: str
    candidate: ToolCandidate
    test_cases: tuple[dict[str, Any], ...]
    revision: int
    static_validation: dict

    def public_manifest(self) -> dict:
        # Source code and test inputs are deliberately not exposed by status.
        return {
            "draft_id": self.draft_id,
            "finding_id": self.finding_id,
            "source_sha256": self.candidate.digest,
            "tool_name": self.candidate.tool_name,
            "revision": self.revision,
            "test_count": len(self.test_cases),
            "static_valid": self.static_validation["valid"],
            "status": "awaiting_local_owner_review",
            "runtime_imported": False,
            "tool_registered": False,
            "independent_attestation": False,
        }


class MutationReviewQueue:
    def __init__(self, *, max_drafts: int = 20, max_revisions: int = 3) -> None:
        if not 1 <= max_drafts <= 100 or not 1 <= max_revisions <= 5:
            raise ValueError("Invalid candidate review budget")
        self._max = max_drafts
        self._revisions = max_revisions
        self._drafts: dict[str, MutationDraft] = {}
        self._validator = CandidateToolValidator()

    def stage(self, *, finding_id: str, candidate: ToolCandidate,
              test_cases: list[dict[str, Any]], revision: int = 1) -> dict:
        if not _ID.fullmatch(finding_id):
            raise ValueError("Unrecognized finding identity")
        if not 1 <= revision <= self._revisions:
            raise ValueError("Revision budget exceeded")
        validation = self._validator.validate(candidate)
        if not validation["valid"]:
            raise ValueError("Unsafe or invalid source proposal")
        if not 1 <= len(test_cases) <= 8:
            raise ValueError("Expected 1..8 review test cases")
        if any(not isinstance(case, dict) or set(case) != {"input", "expected"}
               or not isinstance(case["input"], dict) for case in test_cases):
            raise ValueError("Invalid test-case schema")
        try:
            encoded = json.dumps(test_cases, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Tests must contain JSON values") from exc
        if len(encoded.encode()) > 8192:
            raise ValueError("Test inputs exceed review budget")
        identity = finding_id + ":" + candidate.digest + ":" + str(revision)
        draft_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
        if draft_id not in self._drafts and len(self._drafts) >= self._max:
            raise ValueError("Review queue is full")
        # Store only in this isolated in-memory review queue, not Core sources
        # or persistent skill data. A separate owner plane must manage artifacts.
        draft = MutationDraft(draft_id, finding_id, candidate,
                              tuple(test_cases), revision, validation)
        self._drafts[draft_id] = draft
        return draft.public_manifest()

    def revise(self, existing_id: str, *, candidate: ToolCandidate,
               test_cases: list[dict[str, Any]]) -> dict:
        previous = self._drafts.get(existing_id)
        if previous is None:
            raise KeyError("Unknown review draft")
        return self.stage(
            finding_id=previous.finding_id, candidate=candidate,
            test_cases=test_cases, revision=previous.revision + 1,
        )

    def list_pending(self) -> tuple[dict, ...]:
        return tuple(x.public_manifest() for x in self._drafts.values())

    async def request_smoke_test(
        self, draft_id: str, *, principal_id: str, approval_id: str,
        sandbox: GovernedSandboxReview,
    ) -> SandboxSmokeReport:
        draft = self._drafts.get(draft_id)
        if draft is None:
            raise KeyError("Unknown review draft")
        if principal_id != "local_owner" or not approval_id:
            raise PermissionError("An explicit Local Owner sandbox approval is required")
        # May only execute through MCP Gateway within the isolated sandbox.
        return await sandbox.smoke_test(
            candidate=draft.candidate, cases=list(draft.test_cases),
            principal_id=principal_id, approval_id=approval_id,
        )
