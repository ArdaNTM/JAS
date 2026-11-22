"""Independent, signed and strictly scoped Owner delegation for isolated MCPs.

This is a distinct domain from the original static-review-only delegation.
Owner signing is performed by a separate DPAPI-protected operator identity;
AURA Core receives only the signed document and a pre-pinned public key.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from aura_core.evolution.decision_engine import _DEPLOYED_CATEGORIES
from aura_core.evolution.external_staging import EvolutionWorkspace, _checked_path

DOMAIN = b"AURA:OWNER-ISOLATED-MCP-ACTIVATION:v2\n"
SCHEMA = "aura.owner-autonomy-delegation.v2"
# These fixed, reviewable contracts describe the only allowed execution
# profile and independently observed MCP health checks. Owner cannot choose
# an arbitrary test/policy hash that the attestor merely echoes.
SANDBOX_POLICY = (
    b"AURA:ISOLATED-MCP-DOCKER-POLICY:v1|network=none|read-only-rootfs|"
    b"read-only-source|cap-drop=ALL|no-new-privileges|pids=64|"
    b"memory=256m|cpus=1|user=65534:65534|tmpfs-noexec"
)
SANDBOX_HEALTH_TESTS = (
    b"AURA:MCP-HEALTH-OBSERVATION:v1|initialize|tools/list|"
    b"max-tools=16|schema-bound|runtime-tree-bound"
)
SANDBOX_POLICY_SHA256 = hashlib.sha256(SANDBOX_POLICY).hexdigest()
SANDBOX_TESTS_SHA256 = hashlib.sha256(SANDBOX_HEALTH_TESTS).hexdigest()
_IMAGE = re.compile(r"^[A-Za-z0-9._/-]+@sha256:[a-f0-9]{64}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")
_REQUIRED = {
    "schema", "principal_id", "issued_at", "expires_at",
    "categories", "scope", "auto_activation", "oci_image",
    "policy_sha256", "tests_sha256", "attestor_key_sha256",
    "attestor_runner_id", "max_tools", "min_score",
}


def canonical(claims: dict) -> bytes:
    return DOMAIN + json.dumps(
        claims, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("ascii")


def validated_claims(claims: object, *, now: int | None = None) -> dict:
    if not isinstance(claims, dict) or set(claims) != _REQUIRED:
        raise PermissionError("Unexpected Owner delegation fields")
    current = int(time.time()) if now is None else now
    if (claims["schema"] != SCHEMA
            or claims["principal_id"] != "local_owner"
            or claims["scope"] != "offline-container-stdio"
            or claims["auto_activation"] is not True
            or type(claims["issued_at"]) is not int
            or type(claims["expires_at"]) is not int
            or claims["issued_at"] > current
            or claims["expires_at"] <= current
            or not 60 <= claims["expires_at"] - claims["issued_at"] <= 365 * 86400):
        raise PermissionError("Owner activation scope or lifetime invalid")
    categories = claims["categories"]
    if (not isinstance(categories, list) or not categories
            or any(type(x) is not str for x in categories)
            or len(categories) != len(set(categories))
            or not set(categories) <= _DEPLOYED_CATEGORIES):
        raise PermissionError("Invalid delegated category list")
    if not isinstance(claims["oci_image"], str) or not _IMAGE.fullmatch(claims["oci_image"]):
        raise PermissionError("Unpinned isolated runtime image")
    if any(not isinstance(claims[key], str) or not _SHA.fullmatch(claims[key])
           for key in ("policy_sha256", "tests_sha256", "attestor_key_sha256")):
        raise PermissionError("Independent attestor trust pins missing")
    if (claims["policy_sha256"] != SANDBOX_POLICY_SHA256
            or claims["tests_sha256"] != SANDBOX_TESTS_SHA256):
        raise PermissionError("Unknown or unobserved sandbox policy/test contract")
    if not isinstance(claims["attestor_runner_id"], str) or not _ID.fullmatch(claims["attestor_runner_id"]):
        raise PermissionError("Untrusted attestor identity")
    if (type(claims["max_tools"]) is not int or not 1 <= claims["max_tools"] <= 16
            or type(claims["min_score"]) is not int
            or not 70 <= claims["min_score"] <= 100):
        raise PermissionError("Delegated runtime budget invalid")
    return claims


def _require_readonly_public_owner_mirror(path: Path) -> None:
    """NTFS: Owner/SYSTEM/Admin may write; Authenticated Users may READ only.

    Owner root retains its independent private ACL; only these two public
    signed, non-secret children are readable by the Core/attestor identities.
    """
    if os.name != "nt":
        return
    from aura_core.evolution.windows_owner_storage import _powershell
    script = r"""
$ErrorActionPreference = 'Stop'
try {
    $p = $env:AURA_OWNER_ACL_PATH
    $item = Get-Item -LiteralPath $p -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { exit 10 }
    $acl = Get-Acl -LiteralPath $p
    if (-not $acl.AreAccessRulesProtected) { exit 11 }
    $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($owner -in @('S-1-5-11', 'S-1-1-0', 'S-1-5-32-545')) { exit 12 }
    $self = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $valid = @($owner, $self, 'S-1-5-18', 'S-1-5-32-544', 'S-1-5-11')
    $authRead = $false
    foreach ($ace in $acl.Access) {
        $sid = $ace.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
        if ($sid -notin $valid -or $ace.IsInherited) { exit 13 }
        if ($sid -eq 'S-1-5-11') {
            if ($ace.AccessControlType -ne 'Allow') { exit 14 }
            $forbidden = (
                [Security.AccessControl.FileSystemRights]::WriteData -bor
                [Security.AccessControl.FileSystemRights]::AppendData -bor
                [Security.AccessControl.FileSystemRights]::WriteAttributes -bor
                [Security.AccessControl.FileSystemRights]::WriteExtendedAttributes -bor
                [Security.AccessControl.FileSystemRights]::Delete -bor
                [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
                [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
                [Security.AccessControl.FileSystemRights]::TakeOwnership
            )
            if (($ace.FileSystemRights -band $forbidden) -ne 0) { exit 15 }
            $rx = [Security.AccessControl.FileSystemRights]::ReadAndExecute
            if (($ace.FileSystemRights -band $rx) -ne $rx) { exit 18 }
            $authRead = $true
        } else {
            $full = [Security.AccessControl.FileSystemRights]::FullControl
            if ($ace.AccessControlType -ne 'Allow' -or
                ($ace.FileSystemRights -band $full) -ne $full) { exit 19 }
        }
    }
    if (-not $authRead) { exit 16 }
} catch { exit 17 }
"""
    _powershell(script, path=path)


class ActivationDelegationVerifier:
    def __init__(self, workspace: EvolutionWorkspace):
        self.workspace = workspace

    def _verify_pair(
        self, *, owner: Path, document: Path, public_key: Path,
        pinned: str, shared_readonly: bool,
    ) -> dict | None:
        try:
            if (not owner.is_dir() or owner.is_symlink()
                    or any(p.is_symlink() or not p.is_file() for p in (document, public_key))
                    or document.stat().st_size > 4096
                    or public_key.stat().st_size > 512):
                return None
            _checked_path(owner)
            if os.name == "nt":
                if shared_readonly:
                    for path in (document, public_key):
                        _require_readonly_public_owner_mirror(path)
                else:
                    from aura_core.evolution.windows_owner_storage import require_private_acl
                    for path in (owner, document, public_key):
                        require_private_acl(path)
            else:
                if (owner.stat().st_mode & 0o077
                        or any(p.stat().st_mode & 0o077 for p in (document, public_key))):
                    return None
            key = serialization.load_pem_public_key(public_key.read_bytes())
            if not isinstance(key, Ed25519PublicKey):
                return None
            raw = key.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            )
            if hashlib.sha256(raw).hexdigest() != pinned:
                return None
            payload = json.loads(document.read_text("utf-8"))
            if not isinstance(payload, dict) or set(payload) != {"claims", "signature_b64"}:
                return None
            claims = validated_claims(payload["claims"])
            encoded = payload["signature_b64"]
            if (not isinstance(encoded, str) or len(encoded) != 86
                    or not re.fullmatch(r"[a-zA-Z0-9_-]+", encoded)):
                return None
            signature = base64.urlsafe_b64decode(encoded + "==")
            if (len(signature) != 64 or
                    base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=") != encoded):
                return None
            key.verify(signature, canonical(claims))
            return dict(claims)
        except (OSError, ValueError, TypeError, RuntimeError, PermissionError,
                InvalidSignature, UnicodeError, KeyError):
            return None

    def verified_grant(self) -> dict | None:
        if (os.getenv("AURA_STORAGE_MODE", "").lower() != "local"
                or os.getenv("AURA_EVOLUTION_AUTO_ACTIVATE", "0") != "1"):
            return None
        pinned = os.getenv("AURA_EVOLUTION_DELEGATION_KEY_SHA256", "")
        if not _SHA.fullmatch(pinned):
            return None
        owner = self.workspace.root / "owner"
        private = self._verify_pair(
            owner=owner,
            document=owner / "autonomous_delegation.json",
            public_key=owner / "autonomous_delegation.pub.pem",
            pinned=pinned, shared_readonly=False,
        )
        if private is not None:
            return private
        # Separate restricted Windows Core/attestor accounts cannot open the
        # Owner's private files. Owner publishes only these two signed public
        # mirror children with explicit NTFS READ (no modify/replay) ACEs.
        if os.name == "nt":
            return self._verify_pair(
                owner=owner,
                document=owner / "public-autonomous-delegation.json",
                public_key=owner / "public-autonomous-delegation.pub.pem",
                pinned=pinned, shared_readonly=True,
            )
        return None

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Verify only: independent signed Owner activation")
    parser.add_argument("--verify", action="store_true", required=True)
    parser.add_argument("--evolution-root", type=Path, required=True)
    args = parser.parse_args()
    grant = ActivationDelegationVerifier(
        EvolutionWorkspace(args.evolution_root),
    ).verified_grant()
    return 0 if grant is not None else 3


if __name__ == "__main__":
    raise SystemExit(main())
