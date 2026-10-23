"""Strict read-only access to files beneath the repository's test-data directory."""
from __future__ import annotations

import os
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath

MAX_READ_BYTES = 1_048_576
_WINDOWS_REPARSE_POINT = 0x400


def _is_link_or_reparse_point(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & _WINDOWS_REPARSE_POINT
    )


class SafeReadError(ValueError):
    """A deliberately non-sensitive filesystem read rejection."""


def default_test_data_root() -> Path:
    # safe_reader.py -> filesystem -> aura_core -> src -> core -> repository root
    return Path(__file__).resolve().parents[4] / "test-data"


def read_test_data_file(relative_path: str, *, root: Path | None = None) -> str:
    """Read one UTF-8 regular file from test-data; never write or enumerate."""
    if not isinstance(relative_path, str) or not relative_path or "\x00" in relative_path:
        raise SafeReadError("path must be a non-empty relative path")
    if "\\" in relative_path:
        raise SafeReadError("path must use forward-slash separators")
    win_path = PureWindowsPath(relative_path)
    posix_path = PurePosixPath(relative_path)
    if win_path.is_absolute() or win_path.drive or posix_path.is_absolute():
        raise SafeReadError("absolute paths are not allowed")
    parts = posix_path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise SafeReadError("path traversal is not allowed")

    configured_root = root or default_test_data_root()
    try:
        if _is_link_or_reparse_point(configured_root.lstat()):
            raise SafeReadError("permitted directory cannot be a symbolic link")
        base = configured_root.resolve(strict=True)
    except SafeReadError:
        raise
    except OSError as exc:
        raise SafeReadError("permitted directory is unavailable") from exc
    if not base.is_dir():
        raise SafeReadError("permitted path is not a directory")
    candidate = base
    # Reject symlinks/reparse points in every supplied path component.
    for part in parts:
        candidate = candidate / part
        try:
            component_stat = candidate.lstat()
        except FileNotFoundError as exc:
            raise SafeReadError("file does not exist") from exc
        except OSError as exc:
            raise SafeReadError("file cannot be accessed") from exc
        if _is_link_or_reparse_point(component_stat):
            raise SafeReadError("symbolic links are not allowed")

    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(base)
    except (OSError, ValueError) as exc:
        raise SafeReadError("path is outside the permitted directory or unavailable") from exc

    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(resolved, flags)
        with os.fdopen(descriptor, "rb") as handle:
            file_stat = os.fstat(handle.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                raise SafeReadError("only regular files can be read")
            if file_stat.st_size > MAX_READ_BYTES:
                raise SafeReadError("file exceeds the 1 MiB read limit")
            content = handle.read(MAX_READ_BYTES + 1)
    except SafeReadError:
        raise
    except FileNotFoundError as exc:
        raise SafeReadError("file does not exist") from exc
    except OSError as exc:
        raise SafeReadError("file cannot be accessed") from exc

    if len(content) > MAX_READ_BYTES:
        raise SafeReadError("file exceeds the 1 MiB read limit")
    try:
        return content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SafeReadError("file is not valid UTF-8 text") from exc
