"""Deterministic, principal-labelled in-memory backup integrity envelopes.

The caller MUST authenticate and authorize access to all input bytes upstream.
This format detects accidental corruption but is neither encrypted nor signed.
Verification NEVER writes/restores files or grants an execution capability.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
from dataclasses import dataclass

_SCHEMA = "aura.backup.inline.v1"
_MANIFEST = "manifest.json"
_MAX_FILE = 2 * 1024 * 1024
_MAX_DATA = 8 * 1024 * 1024
_MAX_ARCHIVE = 9 * 1024 * 1024
_MAX_FILES = 50
_PRINCIPAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_SHA = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class BackupEntry:
    path: str
    content_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class BackupInspection:
    scope_sha256: str
    bundle_sha256: str
    entries: tuple[BackupEntry, ...]
    checksums_verified: bool = True
    authenticity_verified: bool = False
    encrypted: bool = False
    authorization_checked: bool = False
    restored: bool = False


def _principal_id(value: str) -> str:
    if type(value) is not str or not _PRINCIPAL.fullmatch(value):
        raise ValueError("invalid principal identity")
    return value


def _path(name: str) -> str:
    if type(name) is not str or not 1 <= len(name) <= 180:
        raise ValueError("invalid backup member path")
    if name.startswith("/") or "\\" in name or ":" in name:
        raise ValueError("unsafe backup member path")
    segments = name.split("/")
    if any(
        not segment or segment in {".", ".."}
        or segment.endswith((" ", "."))
        or len(segment) > 90
        or any(ord(char) < 32 or ord(char) == 127 for char in segment)
        for segment in segments
    ):
        raise ValueError("unsafe backup member path")
    return name


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest_bytes(principal: str, entries: tuple[BackupEntry, ...]) -> bytes:
    manifest = {
        "schema": _SCHEMA,
        "scope_sha256": _digest(principal.encode("utf-8")),
        "entries": [
            {"path": entry.path, "content_sha256": entry.content_sha256,
             "size_bytes": entry.size_bytes}
            for entry in entries
        ],
    }
    return json.dumps(
        manifest, sort_keys=True, ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _insert(archive: zipfile.ZipFile, path: str, content: bytes) -> None:
    info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    archive.writestr(info, content)


def make_backup_bundle(
    files: dict[str, bytes], *, principal_id: str
) -> bytes:
    """Pack already-authorized content into a bounded deterministic envelope."""
    principal = _principal_id(principal_id)
    if type(files) is not dict or not 1 <= len(files) <= _MAX_FILES:
        raise ValueError("backup requires 1..50 explicit files")
    normalized: dict[str, bytes] = {}
    seen: set[str] = set()
    total = 0
    for name, content in files.items():
        checked = _path(name)
        if checked.casefold() == _MANIFEST or checked.casefold() in seen:
            raise ValueError("reserved or duplicate backup file path")
        seen.add(checked.casefold())
        if type(content) is not bytes or len(content) > _MAX_FILE:
            raise ValueError("backup bytes exceed per-file limit")
        total += len(content)
        if total > _MAX_DATA:
            raise ValueError("total backup data exceeds limit")
        normalized[checked] = content
    sorted_paths = sorted(normalized, key=lambda name: (name.casefold(), name))
    entries = tuple(
        BackupEntry(path, _digest(normalized[path]), len(normalized[path]))
        for path in sorted_paths
    )
    index = _manifest_bytes(principal, entries)
    if len(index) > 65536:
        raise ValueError("backup manifest exceeds limit")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", allowZip64=False) as archive:
        _insert(archive, _MANIFEST, index)
        for path in sorted_paths:
            _insert(archive, path, normalized[path])
    result = output.getvalue()
    if len(result) > _MAX_ARCHIVE:
        raise ValueError("backup archive exceeds limit")
    return result


def verify_backup_bundle(
    bundle: bytes, *, principal_id: str
) -> BackupInspection:
    """Verify per-entry checksums and scope label without restoring data.

    SHA-256 is NOT a cryptographic signature: an attacker who can modify the
    payload and manifest together can forge checksums. Never treat this as a
    signed receipt, ownership grant, or independently trusted attestation.
    """
    principal = _principal_id(principal_id)
    if type(bundle) is not bytes or not 1 <= len(bundle) <= _MAX_ARCHIVE:
        raise ValueError("bounded backup archive bytes required")
    try:
        with zipfile.ZipFile(io.BytesIO(bundle), "r") as archive:
            infos = archive.infolist()
            if not 2 <= len(infos) <= _MAX_FILES + 1:
                raise ValueError("invalid backup archive inventory")
            known: dict[str, zipfile.ZipInfo] = {}
            total = 0
            for info in infos:
                name = _path(info.filename)
                if name.casefold() in known:
                    raise ValueError("ambiguous duplicate backup path")
                if info.is_dir() or stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                    raise ValueError("backup directories and links are forbidden")
                if info.flag_bits & 1 or info.compress_type != zipfile.ZIP_STORED:
                    raise ValueError("encrypted or compressed backup entry forbidden")
                cap = 65536 if name.casefold() == _MANIFEST else _MAX_FILE
                if info.file_size > cap or info.compress_size != info.file_size:
                    raise ValueError("backup entry exceeds size/encoding limit")
                total += info.file_size
                if total > _MAX_DATA + 65536:
                    raise ValueError("backup uncompressed budget exceeded")
                known[name.casefold()] = info
            if _MANIFEST not in known:
                raise ValueError("backup manifest missing")

            def read(name: str, size: int) -> bytes:
                with archive.open(known[name.casefold()]) as stream:
                    raw = stream.read(size + 1)
                if len(raw) > size:
                    raise ValueError("backup member read limit exceeded")
                return raw

            raw_index = read(_MANIFEST, 65536)
            try:
                manifest = json.loads(raw_index.decode("utf-8"))
            except (ValueError, UnicodeError) as exc:
                raise ValueError("invalid backup manifest") from exc
            if type(manifest) is not dict or set(manifest) != {
                "schema", "scope_sha256", "entries",
            } or manifest["schema"] != _SCHEMA:
                raise ValueError("invalid backup manifest schema")
            if manifest["scope_sha256"] != _digest(principal.encode("utf-8")):
                raise PermissionError("backup scope does not match")
            records = manifest["entries"]
            if type(records) is not list or not 1 <= len(records) <= _MAX_FILES:
                raise ValueError("invalid backup entries")
            files: list[BackupEntry] = []
            recorded: set[str] = set()
            for record in records:
                if type(record) is not dict or set(record) != {
                    "path", "size_bytes", "content_sha256",
                }:
                    raise ValueError("invalid backup entry metadata")
                path = _path(record["path"])
                if path.casefold() == _MANIFEST or path.casefold() in recorded:
                    raise ValueError("duplicate or reserved manifest member")
                recorded.add(path.casefold())
                digest = record["content_sha256"]
                size = record["size_bytes"]
                if type(digest) is not str or not _SHA.fullmatch(digest):
                    raise ValueError("invalid backup digest")
                if type(size) is not int or not 0 <= size <= _MAX_FILE:
                    raise ValueError("invalid backup size")
                if path.casefold() not in known:
                    raise ValueError("backup manifest references missing entry")
                if known[path.casefold()].filename != path:
                    raise ValueError("backup manifest path case mismatch")
                actual = read(path, _MAX_FILE)
                if len(actual) != size or _digest(actual) != digest:
                    raise ValueError("backup integrity mismatch")
                files.append(BackupEntry(path, digest, size))
            if recorded != set(known) - {_MANIFEST}:
                raise ValueError("backup contains unrecorded members")
    except PermissionError:
        # Cross-principal scope denial is intentional: never disguise it as a
        # corrupt ZIP or silently recover by ignoring the requested identity.
        raise
    except (zipfile.BadZipFile, EOFError, RuntimeError, OSError) as exc:
        raise ValueError("invalid backup ZIP envelope") from exc
    return BackupInspection(
        scope_sha256=_digest(principal.encode("utf-8")),
        bundle_sha256=_digest(bundle),
        entries=tuple(files),
    )
