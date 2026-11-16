"""Descriptor-walk safety: actual POSIX openat and symlink race regression."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from aura_core.filesystem.safe_reader import (
    MAX_READ_BYTES, SafeReadError, read_test_data_file,
)

_HAS_OPENAT = os.name == "posix" and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")
posix_only = pytest.mark.skipif(not _HAS_OPENAT, reason="POSIX descriptor walk needs O_NOFOLLOW")


@posix_only
def test_descriptor_walk_reads_real_nested_utf8_file(tmp_path: Path):
    (tmp_path / "folder").mkdir()
    (tmp_path / "folder" / "a.txt").write_text("Merhaba AURA ✓", encoding="utf-8")
    assert read_test_data_file("folder/a.txt", root=tmp_path) == "Merhaba AURA ✓"


@posix_only
def test_intermediate_component_swap_to_symlink_is_denied(tmp_path: Path, monkeypatch):
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    (outside / "secret.txt").write_text("PRIVATE_SECRET", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "secret.txt").write_text("allowed", encoding="utf-8")
    original_open = os.open
    mutated = False

    def adversarial_open(path, flags, *args, **kwargs):
        nonlocal mutated
        if path == "nested" and "dir_fd" in kwargs and not mutated:
            mutated = True
            nested.rename(tmp_path / "former-nested")
            nested.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", adversarial_open)
    try:
        with pytest.raises(SafeReadError):
            read_test_data_file("nested/secret.txt", root=tmp_path)
        assert mutated
    finally:
        monkeypatch.undo()
        (outside / "secret.txt").unlink()
        outside.rmdir()


@posix_only
def test_final_file_swap_to_symlink_is_denied(tmp_path: Path, monkeypatch):
    outside = tmp_path.parent / (tmp_path.name + "-sensitive.txt")
    outside.write_text("DO_NOT_EXPOSE", encoding="utf-8")
    source = tmp_path / "document.txt"
    source.write_text("safe", encoding="utf-8")
    original_open = os.open
    mutated = False

    def adversarial_open(path, flags, *args, **kwargs):
        nonlocal mutated
        if path == "document.txt" and "dir_fd" in kwargs and not mutated:
            mutated = True
            source.rename(tmp_path / "former-document.txt")
            source.symlink_to(outside)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", adversarial_open)
    try:
        with pytest.raises(SafeReadError):
            read_test_data_file("document.txt", root=tmp_path)
        assert mutated
    finally:
        monkeypatch.undo()
        outside.unlink()


@posix_only
def test_root_swap_to_symlink_is_denied_before_openat(tmp_path: Path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "doc.txt").write_text("in root", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "doc.txt").write_text("OUTSIDE", encoding="utf-8")
    original_open = os.open
    mutated = False

    def adversarial_open(path, flags, *args, **kwargs):
        nonlocal mutated
        if not mutated and os.fspath(path) == os.fspath(allowed.resolve()):
            mutated = True
            allowed.rename(tmp_path / "former-allowed")
            allowed.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", adversarial_open)
    with pytest.raises(SafeReadError):
        read_test_data_file("doc.txt", root=allowed)
    monkeypatch.undo()
    assert mutated


@posix_only
def test_rejects_lexical_dots_and_double_separators(tmp_path: Path):
    (tmp_path / "folder").mkdir()
    (tmp_path / "folder" / "a.txt").write_text("valid", encoding="utf-8")
    for path in ("folder//a.txt", "folder/./a.txt", "./folder/a.txt", "folder/a.txt/"):
        with pytest.raises(SafeReadError, match="traversal"):
            read_test_data_file(path, root=tmp_path)


@posix_only
def test_read_limits_and_invalid_bytes_still_enforced(tmp_path: Path):
    (tmp_path / "huge.txt").write_bytes(b"x" * (MAX_READ_BYTES + 1))
    (tmp_path / "bad.txt").write_bytes(b"\xff\xfe")
    for name, fragment in (("huge.txt", "1 MiB"), ("bad.txt", "UTF-8")):
        with pytest.raises(SafeReadError, match=fragment):
            read_test_data_file(name, root=tmp_path)
