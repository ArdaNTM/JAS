from __future__ import annotations

from pathlib import Path

import pytest

from aura_core.filesystem.safe_reader import (
    MAX_READ_BYTES,
    SafeReadError,
    read_test_data_file,
)


def test_reads_utf8_file_under_root(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "hello.txt").write_text("Merhaba AURA", encoding="utf-8")
    assert read_test_data_file("nested/hello.txt", root=tmp_path) == "Merhaba AURA"


@pytest.mark.parametrize(
    "path",
    [
        "../secret.txt",
        "nested/../../secret.txt",
        "/etc/passwd",
        "C:/Windows/win.ini",
        r"nested\\secret.txt",
        "",
        ".",
    ],
)
def test_rejects_traversal_absolute_and_invalid_paths(tmp_path: Path, path: str) -> None:
    with pytest.raises(SafeReadError):
        read_test_data_file(path, root=tmp_path)


def test_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SafeReadError, match="does not exist"):
        read_test_data_file("missing.txt", root=tmp_path)


def test_rejects_directory(tmp_path: Path) -> None:
    (tmp_path / "folder").mkdir()
    with pytest.raises(SafeReadError):
        read_test_data_file("folder", root=tmp_path)


def test_rejects_oversized_file(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_bytes(b"x" * (MAX_READ_BYTES + 1))
    with pytest.raises(SafeReadError, match="1 MiB"):
        read_test_data_file("large.txt", root=tmp_path)


def test_rejects_invalid_utf8(tmp_path: Path) -> None:
    (tmp_path / "binary.txt").write_bytes(b"\\xff\\xfe")
    with pytest.raises(SafeReadError, match="UTF-8"):
        read_test_data_file("binary.txt", root=tmp_path)


def test_rejects_symlink_to_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-aura-test-secret.txt"
    outside.write_text("not allowed", encoding="utf-8")
    link = tmp_path / "escape.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    try:
        with pytest.raises(SafeReadError, match="symbolic links"):
            read_test_data_file("escape.txt", root=tmp_path)
    finally:
        outside.unlink(missing_ok=True)


def test_rejects_symlinked_directory_component(tmp_path: Path) -> None:
    outside_dir = tmp_path.parent / "outside-aura-test-dir"
    outside_dir.mkdir(exist_ok=True)
    (outside_dir / "secret.txt").write_text("not allowed", encoding="utf-8")
    link = tmp_path / "linked"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    try:
        with pytest.raises(SafeReadError, match="symbolic links"):
            read_test_data_file("linked/secret.txt", root=tmp_path)
    finally:
        (outside_dir / "secret.txt").unlink(missing_ok=True)
        outside_dir.rmdir()


def test_rejects_null_byte(tmp_path: Path) -> None:
    with pytest.raises(SafeReadError):
        read_test_data_file("bad\\x00name.txt", root=tmp_path)


def test_rejects_symlinked_root(tmp_path: Path) -> None:
    actual_root = tmp_path / "actual"
    actual_root.mkdir()
    (actual_root / "secret.txt").write_text("not allowed", encoding="utf-8")
    root_link = tmp_path / "root-link"
    try:
        root_link.symlink_to(actual_root, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(SafeReadError, match="permitted directory"):
        read_test_data_file("secret.txt", root=root_link)
