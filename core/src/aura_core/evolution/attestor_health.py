"""Independent attestor process lock and informational health telemetry.

Neither the lock nor the telemetry grants authority. Only the separately
verified Owner delegation and signed evidence can authorize execution.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

from aura_core.evolution.external_staging import _checked_path


@contextmanager
def attestor_lock(root: Path):
    """Hold an OS lock for the entire process; do not unlink the lock file."""
    _checked_path(root)
    path = root / ".independent-attestor.lock"
    _checked_path(path)
    if path.exists() and not path.is_file():
        raise PermissionError("Unsafe independent attestor lock path")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    locked = False
    try:
        _checked_path(path)
        if os.fstat(fd).st_nlink != 1 or not os.path.samestat(os.fstat(fd), path.stat()):
            raise PermissionError("Independent attestor lock identity changed")
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise PermissionError("Independent attestor already running for this workspace") from exc
        yield
    finally:
        try:
            if locked:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


class AttestorHealth:
    """Heartbeat independent of the scan duration; bounded, atomic metadata."""

    def __init__(self, root: Path):
        self.path = root / "attestor-health.json"
        self._mutex = threading.Lock()
        self._stop = threading.Event()
        previous = read_attestor_health(root)
        self._record = {
            "schema": "aura.independent-attestor-health.v1",
            "pid": os.getpid(), "phase": "STARTING",
            "heartbeat": 0, "last_scan_started": 0,
            "last_success": previous.get("last_success", 0),
            "last_renewal": previous.get("last_renewal", 0),
            "last_error": "",
        }
        self._thread = threading.Thread(target=self._pulse, daemon=True)

    def _write(self):
        with self._mutex:
            self._record["heartbeat"] = int(time.time())
            temp = None
            try:
                _checked_path(self.path)
                fd, temp = tempfile.mkstemp(prefix=".attestor-health-", dir=self.path.parent)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(self._record, stream, sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, self.path)
            except (OSError, ValueError, RuntimeError):
                # Telemetry failure must not publish authorization or stop renewal.
                print("Independent attestor health write failed", file=sys.stderr, flush=True)
            finally:
                if temp is not None:
                    try:
                        os.unlink(temp)
                    except OSError:
                        pass

    def update(self, **fields):
        with self._mutex:
            self._record.update(fields)
        self._write()

    def _pulse(self):
        while not self._stop.wait(15):
            self._write()

    def __enter__(self):
        self._write()
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._stop.set()
        self._thread.join()
        self.update(phase="STOPPED")


def read_attestor_health(root: Path) -> dict:
    """Untrusted display-only input: never derive permissions from this file."""
    path = root / "attestor-health.json"
    unknown = {"state": "UNKNOWN", "last_success": 0, "last_renewal": 0,
               "last_error": "", "heartbeat": 0}
    try:
        _checked_path(path)
        if not path.is_file() or path.stat().st_size > 4096:
            return unknown
        data = json.loads(path.read_text("utf-8"))
        if not isinstance(data, dict) or data.get("schema") != "aura.independent-attestor-health.v1":
            return unknown
        now = int(time.time())
        keys = ("heartbeat", "last_success", "last_renewal", "last_scan_started")
        if any(type(data.get(key)) is not int or not 0 <= data[key] <= now + 30 for key in keys):
            return unknown
        phase = data.get("phase")
        if phase not in {"STARTING", "SCANNING", "IDLE", "ERROR", "STOPPED"}:
            return unknown
        error = data.get("last_error", "")
        if not isinstance(error, str) or len(error) > 80 or not all(
                c.isascii() and (c.isalnum() or c == "_") for c in error):
            return unknown
        state = ("STOPPED" if phase == "STOPPED" else
                 "STALE" if now - data["heartbeat"] > 60 else
                 "DEGRADED" if phase == "SCANNING" and now - data["last_scan_started"] > 600
                 else phase)
        return {**{key: data[key] for key in keys}, "state": state, "last_error": error}
    except (OSError, ValueError, TypeError, RuntimeError):
        return unknown
