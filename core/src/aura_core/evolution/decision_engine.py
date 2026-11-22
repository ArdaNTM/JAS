"""Inert decisions for staged external MCPs; never a runtime activation authority.

A policy score, even with a signed delegation, is NOT a WebAuthn Owner
receipt, an independent sandbox attestation, or MCPGateway authorization.
Runtime promotion must still use the sealed TrustedPromotionBridge protocol.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from aura_core.evolution.external_staging import (
    EvolutionWorkspace, _checked_path, _valid_repository,
)
from aura_core.evolution.self_discovery import PERMITTED_LICENSES

_SHA = re.compile(r"^[0-9a-f]{64}$")
_KEY_B64 = re.compile(r"^[A-Za-z0-9_-]{86}$")
_DEPLOYED_CATEGORIES = frozenset({
    "desktop_automation", "code_analysis", "local_memory",
    "web_research", "developer_tools", "windows_automation",
    "filesystem", "research", "browser",
})
_SIGN_DOMAIN = b"AURA:OWNER-AUTONOMY-DELEGATION:v1\n"
_MAX_REPORT = 16_000
_MAX_DELEGATION = 4096

_CATEGORY_MARKERS = {
    "desktop_automation": ("windows", "desktop", "screen", "automation"),
    "code_analysis": ("code", "repository", "ast", "graph", "search"),
    "local_memory": ("sqlite", "memory", "local database"),
    "web_research": ("httpx", "fetch", "requests", "browser", "web"),
    "developer_tools": ("fastmcp", "git", "developer", "mcp sdk", "python"),
    "windows_automation": ("windows mcp", "cursor", "uia", "keyboard", "mouse", "window"),
    "filesystem": ("filesystem", "directory", "file management", "file access"),
    "research": ("research", "knowledge", "search engine", "information retrieval"),
    "browser": ("browser", "chromium", "playwright", "selenium", "tab automation"),
}


@dataclass(frozen=True, slots=True)
class Decision:
    repository: str
    status: str
    benefit_score: int
    decision_reason: str
    category: str | None
    source_sha256: str | None
    activation_performed: bool = False
    registration_performed: bool = False
    requires_independent_attestation: bool = True
    requires_owner_receipt: bool = True

    def public(self) -> dict[str, Any]:
        return asdict(self)


def _canonical(claims: dict) -> bytes:
    return _SIGN_DOMAIN + json.dumps(
        claims, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")


class AutonomousDelegationVerifier:
    """Verifier-only trust gate; cannot provision a private key or sign consent.

    Owner provisions a delegation in a *different, protected OS identity*.
    The Ed25519 public-key fingerprint is pinned independently by the operator,
    not read from the writable declaration being verified. Only exact category
    scopes and a bounded expiry are accepted. No credential files are created.
    """

    def __init__(self, workspace: EvolutionWorkspace):
        self.workspace = workspace

    def authorized_categories(self) -> frozenset[str]:
        if os.getenv("AURA_STORAGE_MODE", "").lower() != "local":
            return frozenset()
        if os.getenv("AURA_EVOLUTION_AUTO_ACTIVATE", "0") != "1":
            return frozenset()
        fingerprint = os.getenv("AURA_EVOLUTION_DELEGATION_KEY_SHA256", "")
        if not _SHA.fullmatch(fingerprint):
            return frozenset()
        owner = self.workspace.root / "owner"
        declaration = owner / "autonomous_delegation.json"
        keyfile = owner / "autonomous_delegation.pub.pem"
        try:
            if (not owner.is_dir() or owner.is_symlink()
                    or declaration.is_symlink() or keyfile.is_symlink()
                    or not declaration.is_file() or not keyfile.is_file()
                    or declaration.stat().st_size > _MAX_DELEGATION
                    or keyfile.stat().st_size > 512):
                return frozenset()
            # Never follow symlink/junction components when looking up identity.
            _checked_path(owner)
            if os.name == "nt":
                from aura_core.evolution.windows_owner_storage import require_private_acl
                for protected in (owner, declaration, keyfile):
                    require_private_acl(protected)
            key_bytes = keyfile.read_bytes()
            key = serialization.load_pem_public_key(key_bytes)
            if not isinstance(key, Ed25519PublicKey):
                return frozenset()
            raw = key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            if hashlib.sha256(raw).hexdigest() != fingerprint:
                return frozenset()
            payload = json.loads(declaration.read_text("utf-8"))
            if (not isinstance(payload, dict)
                    or set(payload) != {"claims", "signature_b64"}
                    or not isinstance(payload["claims"], dict)
                    or not isinstance(payload["signature_b64"], str)):
                return frozenset()
            claims = payload["claims"]
            if set(claims) != {
                "schema", "principal_id", "issued_at", "expires_at",
                "categories", "scope", "auto_activation",
            }:
                return frozenset()
            if (claims["schema"] != "aura.owner-autonomy-delegation.v1"
                    or claims["principal_id"] != "local_owner"
                    or claims["scope"] != "static-review-only"
                    or claims["auto_activation"] is not False
                    or type(claims["issued_at"]) is not int
                    or type(claims["expires_at"]) is not int):
                return frozenset()
            now = int(time.time())
            if (not claims["issued_at"] <= now < claims["expires_at"]
                    or claims["expires_at"] - claims["issued_at"] > 30 * 86400):
                return frozenset()
            categories = claims["categories"]
            if (not isinstance(categories, list)
                    or not categories or len(categories) > 5
                    or any(not isinstance(x, str) for x in categories)
                    or len(set(categories)) != len(categories)
                    or not set(categories) <= _DEPLOYED_CATEGORIES):
                return frozenset()
            signature_b64 = payload["signature_b64"]
            if len(signature_b64) != 86 or not re.fullmatch(r"[A-Za-z0-9_-]+", signature_b64):
                return frozenset()
            signature = base64.urlsafe_b64decode(signature_b64 + "==")
            if len(signature) != 64:
                return frozenset()
            key.verify(signature, _canonical(claims))
            return frozenset(categories)
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, InvalidSignature, RuntimeError):
            return frozenset()


class EvolutionDecisionEngine:
    """Score verified static evidence; never execute or mutate live registries."""

    def __init__(self, workspace: EvolutionWorkspace):
        self.workspace = workspace
        self.delegations = AutonomousDelegationVerifier(workspace)

    def _check_candidate(self, name: str) -> tuple[dict, str, str]:
        package = self.workspace.root / "verified" / name
        if (not _valid_repository(name.replace("__", "/"))
                or name.count("__") != 1 or package.is_symlink()
                or not package.is_dir()):
            raise ValueError("Invalid static package identity")
        _checked_path(package)
        manifest = package / "aura-capability-manifest.json"
        archive = package / "source.zip"
        if (manifest.is_symlink() or archive.is_symlink()
                or not manifest.is_file() or not archive.is_file()
                or manifest.stat().st_size > _MAX_REPORT):
            raise ValueError("Static evidence missing or unsafe")
        data = json.loads(manifest.read_text("utf-8"))
        repository = name.replace("__", "/")
        digest = data.get("source_sha256")
        if (data.get("repository") != repository
                or data.get("status") != "READY_FOR_OWNER_REVIEW"
                or data.get("sandbox_attested") is not False
                or data.get("activation_performed") is not False
                or data.get("execution_allowed") is not False
                or not isinstance(digest, str) or not _SHA.fullmatch(digest)):
            raise ValueError("Manifest is not eligible static evidence")
        hasher = hashlib.sha256()
        with archive.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                hasher.update(chunk)
        if hasher.hexdigest() != digest:
            raise ValueError("Static source SHA-256 mismatch")
        return data, repository, digest

    def evaluate(self, name: str, *, active_categories: frozenset[str] = frozenset()) -> Decision:
        try:
            data, repository, digest = self._check_candidate(name)
        except (OSError, ValueError, TypeError, KeyError, UnicodeError):
            return Decision(name, "REJECTED_EVIDENCE", 0, "Missing/mismatched static evidence", None, None)

        if data.get("license_spdx_metadata") not in PERMITTED_LICENSES:
            return Decision(repository, "REJECTED_POLICY", 0, "License outside local open-source allowlist", None, digest)
        entrypoint = data.get("entrypoint_hint", "")
        if (not isinstance(entrypoint, str) or not 1 <= len(entrypoint) <= 200
                or ".." in Path(entrypoint).parts or entrypoint.startswith("/")
                or "\\" in entrypoint):
            return Decision(repository, "REJECTED_POLICY", 0, "No safe MCP entrypoint hint", None, digest)
        features = data.get("detected_capabilities", [])
        if not isinstance(features, list) or len(features) > 30:
            return Decision(repository, "REJECTED_POLICY", 0, "Invalid capability evidence", None, digest)
        text = (" ".join([repository, entrypoint] + [
            x[:80] for x in features if isinstance(x, str)
        ])).casefold()
        categories = sorted(
            ((sum(term in text for term in terms), category)
             for category, terms in _CATEGORY_MARKERS.items()),
            reverse=True,
        )
        matches, category = categories[0]
        if matches == 0:
            return Decision(repository, "REJECTED_POLICY", 10, "No supported local MCP utility category", None, digest)
        score = min(100, 50 + 10 * matches + (15 if category not in active_categories else 0))
        if category in active_categories:
            return Decision(repository, "DUPLICATE_CAPABILITY", score,
                            "Similar category is already active", category, digest)

        from aura_core.evolution.activation_delegation import ActivationDelegationVerifier
        grant = ActivationDelegationVerifier(self.workspace).verified_grant()
        if (grant is not None and category in grant["categories"]
                and score >= grant["min_score"]):
            # Delegated approval covers the *policy decision only*. Actual
            # execution still requires an independent signed sandbox result,
            # a live healthy isolated provider, and MCPGateway authorization.
            return Decision(repository, "AUTO_APPROVED_BY_POLICY", score,
                            "Delegated offline MCP utility; signed independent sandbox evidence still required",
                            category, digest, requires_owner_receipt=False)
        permitted = self.delegations.authorized_categories()
        if category not in permitted:
            return Decision(repository, "OWNER_DELEGATION_REQUIRED", score,
                            "Requires independently signed, scoped Owner delegation", category, digest)
        # A verified *review decision* does not bypass independent execution
        # attestation, GovernedSkillRegistry or the one-shot Owner receipt.
        return Decision(repository, "POLICY_ELIGIBLE_PENDING_ATTESTATION", score,
                        "Useful local MCP; independent sandbox attestation and signed Owner receipt still required",
                        category, digest)

    def evaluate_pending(self, *, limit: int = 100) -> list[Decision]:
        base = self.workspace.root / "verified"
        result: list[Decision] = []
        for path in sorted(base.iterdir()):
            if len(result) >= min(100, max(1, limit)):
                break
            if path.is_dir() and not path.is_symlink():
                result.append(self.evaluate(path.name))
        return result
