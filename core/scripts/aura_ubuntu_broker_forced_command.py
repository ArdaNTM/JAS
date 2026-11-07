"""Linux unprivileged OpenSSH forced-command front end (INACTIVE).

SSHD authenticates a dedicated key for aura-transport and forces this exact
root-owned file. This front end has NO Docker access and must NOT run as root.
It forwards one bounded JSON frame to the separately started Unix-socket
helper; the helper authenticates the actual kernel peer UID with SO_PEERCRED.
"""
from __future__ import annotations

import os
import socket
import sys

SOCKET_PATH = "/run/aura-osworld-broker/audit.sock"
REMOTE_COMMAND = "aura-osworld-transport-v1"
SSH_USER = "aura-transport"
MAX_REQUEST = 1400
MAX_RESPONSE = 2_000_000


def main() -> int:
    if os.name != "posix" or os.environ.get("SSH_ORIGINAL_COMMAND") != REMOTE_COMMAND:
        return 2
    try:
        import pwd  # Linux only; no import-time Windows CI dependency.
        user = pwd.getpwnam(SSH_USER)
        if user.pw_uid == 0 or os.geteuid() != user.pw_uid or os.getuid() != user.pw_uid:
            return 2
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if not 1 <= len(raw) <= MAX_REQUEST:
            return 2
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(40)
            conn.connect(SOCKET_PATH)
            conn.sendall(raw)
            conn.shutdown(socket.SHUT_WR)
            chunks = []
            size = 0
            while chunk := conn.recv(65536):
                size += len(chunk)
                if size > MAX_RESPONSE:
                    return 2
                chunks.append(chunk)
        if size == 0:
            return 2
        sys.stdout.buffer.write(b"".join(chunks))
        return 0
    except (OSError, LookupError, ValueError):
        # Deliberately never emit traceback or privileged backend stderr.
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
