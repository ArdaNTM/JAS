"""All-or-nothing in-memory text-patch preview and exact-hash undo.

The caller must authorize filesystem/repository access through existing
AURA PermissionEngine/MCP Gateway. This module NEVER reads/writes a path,
invokes a shell, commits to Git, or authorizes an actual rollback.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_SCOPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_FILE_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}\Z", re.ASCII)
_HASH = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class TextPatchRequest:
    relative_path: str
    expected_sha256: str
    old_text: str
    new_text: str


@dataclass(frozen=True, slots=True)
class TextPatchRecord:
    relative_path: str
    original_sha256: str
    proposed_sha256: str
    offset: int
    old_text: str
    new_text: str


@dataclass(frozen=True, slots=True)
class TextTransactionPreview:
    records: tuple[TextPatchRecord, ...]
    proposed_files: tuple[tuple[str, str], ...]
    principal_scope_sha256: str
    task_scope_sha256: str
    transaction_fingerprint: str
    untrusted_data: bool = True
    authorization_checked: bool = False
    filesystem_changed: bool = False
    rollback_executed: bool = False


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scope(value: str) -> str:
    if type(value) is not str or not _SCOPE.fullmatch(value):
        raise ValueError("invalid exact transaction scope")
    return value


def _path(value: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 200:
        raise ValueError("invalid relative path")
    parts = value.split("/")
    if any(
        not _FILE_PART.fullmatch(part) or part in {".", ".."}
        or part.endswith(".") for part in parts
    ):
        raise ValueError("unsafe relative path")
    return value


def _text(value: str, max_size: int) -> str:
    if type(value) is not str or "\x00" in value:
        raise ValueError("invalid patch text")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise ValueError("invalid patch Unicode") from exc
    if size > max_size:
        raise ValueError("patch text exceeds size limit")
    return value


def _fingerprint(records: tuple[TextPatchRecord, ...]) -> str:
    return _digest("".join(
        record.relative_path + "\0" + record.original_sha256 + "\0"
        + record.proposed_sha256 + "\n" for record in records
    ))


def preview_text_transaction(
    files: dict[str, str],
    changes: tuple[TextPatchRequest, ...], *,
    principal_id: str, task_id: str,
) -> TextTransactionPreview:
    """Compute a bounded batch without changing any source dictionary/files."""
    principal, task = _scope(principal_id), _scope(task_id)
    if type(files) is not dict or not 1 <= len(files) <= 32:
        raise ValueError("1..32 original text files required")
    if type(changes) is not tuple or not 1 <= len(changes) <= 16:
        raise ValueError("1..16 patch requests required")
    sources: dict[str, str] = {}
    seen: set[str] = set()
    total = 0
    for path, value in files.items():
        name = _path(path)
        if name.casefold() in seen:
            raise ValueError("ambiguous duplicate file path")
        seen.add(name.casefold())
        sources[name] = _text(value, 65536)
        total += len(sources[name].encode("utf-8"))
        if total > 262144:
            raise ValueError("file snapshot byte budget exceeded")

    proposed: dict[str, str] = {}
    records: list[TextPatchRecord] = []
    touched: set[str] = set()
    for change in changes:
        if type(change) is not TextPatchRequest:
            raise ValueError("TextPatchRequest required")
        name = _path(change.relative_path)
        if name not in sources or name in touched:
            raise ValueError("missing or duplicate patch target")
        touched.add(name)
        expected = change.expected_sha256
        if type(expected) is not str or not _HASH.fullmatch(expected):
            raise ValueError("invalid preimage SHA-256")
        before = sources[name]
        original_sha = _digest(before)
        if original_sha != expected:
            raise ValueError("stale patch preimage SHA-256")
        old = _text(change.old_text, 4096)
        new = _text(change.new_text, 4096)
        if not old or old == new or before.count(old) != 1:
            raise ValueError("ambiguous or no-op patch fragment")
        offset = before.index(old)
        changed = before[:offset] + new + before[offset + len(old):]
        _text(changed, 65536)
        proposed[name] = changed
        records.append(TextPatchRecord(
            relative_path=name, original_sha256=original_sha,
            proposed_sha256=_digest(changed), offset=offset,
            old_text=old, new_text=new,
        ))
    records.sort(key=lambda item: item.relative_path)
    ordered = tuple(records)
    return TextTransactionPreview(
        records=ordered,
        proposed_files=tuple(sorted(proposed.items())),
        principal_scope_sha256=_digest(principal),
        task_scope_sha256=_digest(task),
        transaction_fingerprint=_fingerprint(ordered),
    )


def preview_text_rollback(
    preview: TextTransactionPreview, current_files: dict[str, str], *,
    principal_id: str, task_id: str,
) -> dict[str, str]:
    """Return original bytes-as-text only if the full proposed state is exact.

    Rollback is in-memory reconstruction; no filesystem mutation occurs.
    """
    principal, task = _scope(principal_id), _scope(task_id)
    if type(preview) is not TextTransactionPreview or type(current_files) is not dict:
        raise ValueError("valid preview and current files required")
    if (
        preview.authorization_checked or preview.filesystem_changed
        or preview.rollback_executed or not preview.untrusted_data
    ):
        raise ValueError("forged transaction authority flags")
    if (
        preview.principal_scope_sha256 != _digest(principal)
        or preview.task_scope_sha256 != _digest(task)
    ):
        raise PermissionError("transaction rollback scope mismatch")
    if (
        not 1 <= len(preview.records) <= 16
        or preview.transaction_fingerprint != _fingerprint(preview.records)
    ):
        raise ValueError("invalid transaction fingerprint")
    if set(current_files) != {record.relative_path for record in preview.records}:
        raise ValueError("rollback file inventory mismatch")
    restored: dict[str, str] = {}
    for record in preview.records:
        name = _path(record.relative_path)
        current = _text(current_files[name], 65536)
        if _digest(current) != record.proposed_sha256:
            raise ValueError("rollback preimage mismatch")
        if (
            type(record.offset) is not int or not 0 <= record.offset <= len(current)
            or current[record.offset:record.offset + len(record.new_text)]
               != record.new_text
        ):
            raise ValueError("rollback splice position mismatch")
        original = (
            current[:record.offset] + record.old_text
            + current[record.offset + len(record.new_text):]
        )
        if _digest(original) != record.original_sha256:
            raise ValueError("rollback original hash mismatch")
        restored[name] = original
    return restored
