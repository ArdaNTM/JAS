"""Quarantined model-drafted MCP tools: human-reviewed activation only.

Never import model-generated Python into Core or rewrite the release manifest.
Sources remain outside the release-locked JAS checkout; separate OS principals
must operate the Owner Control Plane and the independent sandbox attestor.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aura_core.application.self_tool_synthesis import CandidateToolValidator, ToolCandidate
from aura_core.evolution.skill_registry import GovernedSkillRegistry, SkillBinding
from aura_core.evolution.owner_receipt import DurableOwnerReceiptConsumer
from aura_core.evolution.durable_attestation import DurableAttestationReceiptRegistry
from aura_core.kernel.events import EventBus, EventPriority, KernelEvent

_DRAFT_ID = re.compile(r"^[a-f0-9]{24}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_OWNER_GUARD = (
    "\n\n# Owner guard is defense-in-depth, not an authorization mechanism.\n"
    "PermissionDenied = PermissionError\n"
    "def invoke(data, principal):\n"
    '    if principal != "local_owner":\n'
    '        raise PermissionDenied("This autonomous capability is restricted to Local Owner.")\n'
    "    return run(data)\n"
)


class DraftRejected(PermissionError):
    """A proposal violated the quarantine or independent approval contract."""


@dataclass(frozen=True, slots=True)
class ReviewDraft:
    draft_id: str
    source_sha256: str
    tool_name: str
    test_count: int

    def public(self) -> dict[str, Any]:
        """Expose only metadata; no generated code, secrets or test inputs."""
        return {
            "draft_id": self.draft_id,
            "source_sha256": self.source_sha256,
            "tool_name": self.tool_name,
            "test_count": self.test_count,
            "status": "awaiting_local_owner_review",
            "independent_attestation": False,
            "tool_registered": False,
            "approval_granted": False,
        }


class EvolutionReviewGateway:
    """Persist non-importable drafts in a private, preprovisioned directory.

    The path MUST be absolute, outside the immutable checkout, free of symlink
    components at the leaf, and independently provisioned with private ACLs.
    Existing paths are never overwritten; file names are derived from hashes.
    """

    def __init__(
        self, *, directory: str | Path, checkout_root: str | Path,
        event_bus: EventBus, max_drafts: int = 64,
    ) -> None:
        if not 1 <= max_drafts <= 128:
            raise ValueError("Invalid draft inventory limit")
        root = Path(checkout_root).resolve(strict=True)
        if not (root / "core" / "src" / "aura_core").is_dir():
            raise DraftRejected("A real JAS checkout root is required")
        dest = Path(directory)
        if not dest.is_absolute() or not dest.is_dir() or dest.is_symlink():
            raise DraftRejected("Preprovisioned private absolute draft directory required")
        dest = dest.resolve(strict=True)
        if dest.is_relative_to(root):
            raise DraftRejected("Drafts cannot be written inside the JAS checkout")
        if os.name == "nt":
            from aura_core.evolution.windows_owner_storage import require_private_acl
            require_private_acl(dest)
        elif os.name == "posix":
            info = dest.stat()
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
                raise DraftRejected("Draft directory must be owner-only (mode 0700)")
        else:
            raise DraftRejected("Unsupported filesystem security policy")
        self._directory = dest
        self._events = event_bus
        self._max_drafts = max_drafts
        self._validator = CandidateToolValidator()
        self._lock = threading.RLock()

    @staticmethod
    def protected_candidate(candidate: ToolCandidate) -> ToolCandidate:
        """Produce digest-bound code with an owner-only entrypoint.

        The actual execution authorization remains entirely in PermissionEngine
        and the MCP Gateway; AST validation and this guard are not a sandbox.
        """
        if not isinstance(candidate, ToolCandidate):
            raise TypeError("Expected ToolCandidate")
        if _OWNER_GUARD in candidate.source_code:
            raise DraftRejected("The guard must only be inserted by trusted code")
        return ToolCandidate(
            tool_name=candidate.tool_name,
            description=candidate.description,
            source_code=candidate.source_code.rstrip() + _OWNER_GUARD,
            input_schema=candidate.input_schema,
            output_schema=candidate.output_schema,
        )

    @staticmethod
    def _encode(value: dict[str, Any]) -> bytes:
        return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                           separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")

    def _create_file(self, basename: str, content: bytes) -> None:
        if len(content) > 32768:
            raise ValueError("Review artifact exceeds 32 KiB budget")
        target = self._directory / basename
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(target, flags, 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=True) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name == "nt":
                from aura_core.evolution.windows_owner_storage import harden_private_acl
                harden_private_acl(target)
        except BaseException:
            target.unlink(missing_ok=True)
            raise

    def stage(self, candidate: ToolCandidate, *, test_count: int) -> ReviewDraft:
        """Quarantine a statically checked draft; publish metadata-only review event.

        Smoke tests are provisional evidence. No signed attestation is issued
        and no source is imported, executed or registered here.
        """
        if not 1 <= test_count <= 8:
            raise ValueError("Expected 1..8 test cases")
        wrapped = self.protected_candidate(candidate)
        if not self._validator.validate(candidate)["valid"]:
            raise DraftRejected("Candidate static validation failed")
        if not self._validator.validate(wrapped)["valid"]:
            raise DraftRejected("Guarded candidate static validation failed")
        draft_id = hashlib.sha256(
            f"{wrapped.tool_name}:{wrapped.digest}".encode("ascii")
        ).hexdigest()[:24]
        draft = ReviewDraft(draft_id, wrapped.digest, wrapped.tool_name, test_count)
        with self._lock:
            if len(list(self._directory.glob("*.review.json"))) >= self._max_drafts:
                raise DraftRejected("Review queue capacity exceeded")
            source_name = f"{draft_id}.review.py.txt"
            self._create_file(source_name, wrapped.source_code.encode("utf-8"))
            try:
                self._create_file(f"{draft_id}.review.json", self._encode(draft.public()))
            except BaseException:
                (self._directory / source_name).unlink(missing_ok=True)
                raise
        self._events.publish(KernelEvent(
            event_type="EvolutionReviewRequest",
            source_component="aura.evolution.review_gateway",
            payload=draft.public(), correlation_id=draft.draft_id,
            priority=EventPriority.HIGH,
        ))
        return draft

    def pending(self, *, limit: int = 20) -> tuple[dict[str, Any], ...]:
        """Read metadata only. The HUD must never receive approval authority."""
        if not 1 <= limit <= 50:
            raise ValueError("Expected bounded review limit")
        with self._lock:
            items: list[dict[str, Any]] = []
            for path in sorted(self._directory.glob("*.review.json"))[:limit]:
                if path.is_symlink() or path.stat().st_size > 4096:
                    raise DraftRejected("Invalid review metadata")
                record = json.loads(path.read_text(encoding="ascii"))
                if not isinstance(record, dict) or not _DRAFT_ID.fullmatch(
                    str(record.get("draft_id", ""))
                ):
                    raise DraftRejected("Invalid review record")
                items.append({key: record[key] for key in (
                    "draft_id", "source_sha256", "tool_name", "test_count",
                    "status", "independent_attestation",
                    "tool_registered", "approval_granted",
                )})
            return tuple(items)

    def activate_pre_registered(
        self, *, draft_id: str, binding: SkillBinding, sandbox_receipt: str,
        owner_receipt: str, registrar: GovernedSkillRegistry,
        owner_receipts: DurableOwnerReceiptConsumer,
        attestations: DurableAttestationReceiptRegistry,
        principal_id: str,
    ) -> str:
        """Only bind a *pre-installed* healthy MCP provider after both proofs.

        An independently signed sandbox attestation AND the separately issued
        one-time WebAuthn owner receipt are verified by the registrar. Runtime
        generation/import and release-manifest mutation remain forbidden.
        """
        if principal_id != "local_owner":
            raise DraftRejected("Only Local Owner can activate reviewed skills")
        if (not isinstance(registrar, GovernedSkillRegistry)
                or not isinstance(owner_receipts, DurableOwnerReceiptConsumer)
                or not isinstance(attestations, DurableAttestationReceiptRegistry)
                or registrar._owner is not owner_receipts
                or registrar._signed is None):
            raise DraftRejected("Independent attestation and owner receipt verifiers required")
        if not _DRAFT_ID.fullmatch(draft_id) or not _SHA256.fullmatch(binding.source_sha256):
            raise ValueError("Invalid draft identity")
        with self._lock:
            # Resolve by exact digest-derived identity: pending() intentionally
            # paginates HUD data and must not limit owner activation lookup.
            record_path = self._directory / f"{draft_id}.review.json"
            if (not record_path.is_file() or record_path.is_symlink()
                    or record_path.stat().st_size > 4096):
                raise DraftRejected("Missing or invalid immutable review metadata")
            record = json.loads(record_path.read_text(encoding="ascii"))
            if not isinstance(record, dict) or record.get("draft_id") != draft_id:
                raise DraftRejected("Review metadata identity mismatch")
            if record["source_sha256"] != binding.source_sha256:
                raise DraftRejected("Binding source differs from immutable reviewed draft")
            if record["tool_name"] != binding.name:
                raise DraftRejected("Tool name differs from reviewed draft")
            artifact = self._directory / f"{draft_id}.review.py.txt"
            if (not artifact.is_file() or artifact.is_symlink()
                    or artifact.stat().st_size > 32768
                    or hashlib.sha256(artifact.read_bytes()).hexdigest()
                       != binding.source_sha256):
                raise DraftRejected("Quarantined source has changed since review")
            if not sandbox_receipt or not owner_receipt:
                raise DraftRejected("Independent evidence and owner receipt are mandatory")
            if not attestations.verify_binding(binding, sandbox_receipt):
                raise DraftRejected("Signed sandbox attestation is invalid")
            registrar.stage(binding)
            registrar.validate(binding.name, sandbox_receipt=sandbox_receipt)
            return registrar.activate(
                binding.name, principal_id=principal_id, owner_receipt=owner_receipt,
            )

    @staticmethod
    def release_handoff() -> dict[str, bool]:
        """An independently signed, manually reviewed release must run CI."""
        return {
            "requires_owner_webauthn": True,
            "requires_signed_sandbox_attestation": True,
            "requires_separate_human_release": True,
            "may_import_untrusted_code": False,
            "may_run_generate_final_lock": False,
        }
