"""F2.6 root-owned, systemd socket-activated AURA Docker audit helper (INACTIVE).

Root is required only here, NEVER in the OpenSSH session. The socket must be
created by systemd with root ownership and aura-transport group traversal; the
helper validates the actual kernel peer identity via SO_PEERCRED. No shell,
Docker daemon TCP listener, broad sudoers entry or docker-group access.

Deployment is intentionally absent and deny_only remains unchanged.
"""
from __future__ import annotations

from contextlib import closing
import os
from pathlib import Path
import socket
import sqlite3
import stat
import struct
import sys
import time

import aura_ubuntu_broker_policy as policy

SOCKET_PATH = "/run/aura-osworld-broker/audit.sock"
NONCE_DB = Path("/var/lib/aura-osworld-broker/nonces.sqlite3")
SSH_USER = "aura-transport"
_BANNED_GROUPS = frozenset({"docker", "sudo", "lxd", "root", "wheel"})


def _require_root_storage(path: Path) -> None:
    parent = path.parent
    p = parent.lstat()
    if not stat.S_ISDIR(p.st_mode) or p.st_uid != 0 or p.st_mode & 0o077:
        raise policy.Denied("Nonce store directory is not root-private")
    try:
        f = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(f.st_mode) or f.st_uid != 0 or f.st_mode & 0o177:
        raise policy.Denied("Nonce store file is not a root-private regular file")


class DurableNonceStore:
    """Atomic INSERT under SQLite immediate transaction; survives restarts."""

    def __init__(self, path: Path = NONCE_DB, *, enforce_root: bool = True) -> None:
        if not isinstance(path, Path) or (enforce_root and path != NONCE_DB):
            raise policy.Denied("Unpinned nonce state")
        self.path = path
        self.enforce_root = enforce_root
        if enforce_root:
            if os.geteuid() != 0:
                raise policy.Denied("Nonce store must run under root helper")
            _require_root_storage(path)
        with closing(self._connection()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS consumed ("
                       "nonce TEXT PRIMARY KEY, run_id TEXT NOT NULL, "
                       "vm_id TEXT NOT NULL, seen_at INTEGER NOT NULL)")
            db.commit()

    def _connection(self) -> sqlite3.Connection:
        if self.enforce_root:
            _require_root_storage(self.path)
        # File creation is protected by an operator-owned 0700 directory.
        prior = os.umask(0o077)
        try:
            db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        finally:
            os.umask(prior)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA busy_timeout=5000")
        if self.enforce_root:
            _require_root_storage(self.path)
        return db

    def claim(self, nonce: str, run_id: str, vm_id: str) -> bool:
        if (type(nonce) is not str or policy.HEX32.fullmatch(nonce) is None
                or type(run_id) is not str or policy.HEX32.fullmatch(run_id) is None
                or type(vm_id) is not str or policy.HEX64.fullmatch(vm_id) is None):
            raise policy.Denied("Invalid nonce ownership")
        with closing(self._connection()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                # Expiry cleanup cannot permit replay within the 30 s freshness
                # window; retain consumed nonces for 24 hours.
                db.execute("DELETE FROM consumed WHERE seen_at < ?", (int(time.time()) - 86400,))
                inserted = db.execute(
                    "INSERT OR IGNORE INTO consumed(nonce,run_id,vm_id,seen_at) VALUES (?,?,?,?)",
                    (nonce, run_id, vm_id, int(time.time())),
                ).rowcount == 1
                db.commit()
                return inserted
            except sqlite3.Error as exc:
                db.rollback()
                raise policy.Denied("Nonce store unavailable") from exc


def _expected_peer_uid() -> int:
    if os.geteuid() != 0:
        raise policy.Denied("Privileged helper is not root-owned")
    import pwd
    import grp
    item = pwd.getpwnam(SSH_USER)
    if item.pw_uid <= 0 or item.pw_name != SSH_USER:
        raise policy.Denied("Missing dedicated unprivileged SSH identity")
    primary = grp.getgrgid(item.pw_gid).gr_name
    memberships = {group.gr_name for group in grp.getgrall() if item.pw_name in group.gr_mem}
    if _BANNED_GROUPS.intersection(memberships | {primary}):
        raise policy.Denied("SSH principal has prohibited local privileges")
    return item.pw_uid


def _peer_uid(connection: socket.socket) -> int:
    """Never trust a JSON-supplied uid or the SSH caller's environment."""
    option = getattr(socket, "SO_PEERCRED", None)
    family = getattr(socket, "AF_UNIX", None)
    if type(option) is not int or family is None or connection.family != family:
        raise policy.Denied("Kernel peer credentials are unavailable")
    creds = connection.getsockopt(socket.SOL_SOCKET, option, struct.calcsize("3i"))
    pid, uid, gid = struct.unpack("3i", creds)
    if pid <= 0 or uid <= 0 or gid < 0:
        raise policy.Denied("Malformed kernel credentials")
    return uid


def handle_connection(connection: socket.socket, *, store: DurableNonceStore,
                      expected_uid: int) -> None:
    """Reply once or close without output. Never return Python/Docker errors."""
    if type(expected_uid) is not int or expected_uid <= 0 or _peer_uid(connection) != expected_uid:
        raise policy.Denied("Unauthorized Unix-socket peer")
    connection.settimeout(180)
    raw = bytearray()
    while chunk := connection.recv(min(4096, policy.MAX_REQUEST + 1 - len(raw))):
        raw.extend(chunk)
        if len(raw) > policy.MAX_REQUEST:
            raise policy.Denied("Oversized root-helper request")
    response = policy.process_request(bytes(raw), claim_nonce=store.claim)
    connection.sendall(response)


def _systemd_listener() -> socket.socket:
    if (os.environ.get("LISTEN_FDS") != "1"
            or os.environ.get("LISTEN_PID") != str(os.getpid())):
        raise policy.Denied("Root helper requires exactly one systemd socket")
    conn = socket.socket(fileno=3)
    if conn.family != socket.AF_UNIX or conn.type & socket.SOCK_STREAM != socket.SOCK_STREAM:
        raise policy.Denied("Untrusted listener type")
    if conn.getsockname() != SOCKET_PATH:
        raise policy.Denied("Unpinned root-helper Unix socket")
    return conn


def _require_sealed_worker() -> None:
    for path in (Path(__file__), Path(policy.__file__)):
        item = path.lstat()
        if (not stat.S_ISREG(item.st_mode) or item.st_uid != 0
                or item.st_mode & 0o022 or not path.is_absolute()):
            raise policy.Denied("Root helper code is not sealed")
        parent = path.parent.lstat()
        if parent.st_uid != 0 or not stat.S_ISDIR(parent.st_mode) or parent.st_mode & 0o022:
            raise policy.Denied("Untrusted executable directory")


def main() -> int:
    try:
        _require_sealed_worker()
        uid = _expected_peer_uid()
        store = DurableNonceStore()
        listener = _systemd_listener()
    except (policy.Denied, OSError, sqlite3.Error, KeyError):
        return 2
    with listener:
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return 2
            with connection:
                try:
                    handle_connection(connection, store=store, expected_uid=uid)
                except (policy.Denied, OSError, sqlite3.Error, ValueError, KeyError):
                    # Reject silently; never turn an error into attestation.
                    continue


if __name__ == "__main__":
    raise SystemExit(main())
