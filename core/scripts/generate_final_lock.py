from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    ".aura-backup",
}


def git_commit() -> str:
    try:
        return subprocess.check_output(
            [
                "git",
                "rev-parse",
                "HEAD",
            ],
            cwd=ROOT,
            text=True,
        ).strip()
    except Exception:
        return "uncommitted"


def included(path: Path) -> bool:
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False

    if path.name.endswith(".aura-backup"):
        return False

    if path.name.endswith(".pyc"):
        return False

    return path.is_file()


def files_to_hash() -> list[Path]:
    roots = (
        ROOT / "core" / "src",
        ROOT / "core" / "pyproject.toml",
        ROOT / "core" / "uv.lock",
        ROOT / "aura-ui" / "src",
        ROOT / "aura-ui" / "package.json",
        ROOT / "aura-ui" / "package-lock.json",
    )

    result: list[Path] = []

    for root in roots:
        if root.is_file():
            if included(root):
                result.append(root)
            continue

        if root.exists():
            result.extend(
                path
                for path in root.rglob("*")
                if included(path)
            )

    return sorted(
        set(result),
        key=lambda path: str(path.relative_to(ROOT)).lower(),
    )


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def compute_release_digest(
    entries: list[tuple[str, str]],
) -> str:
    digest = hashlib.sha256()

    for relative, file_digest in entries:
        line = f"{relative}\t{file_digest}\n".encode(
            "utf-8"
        )
        digest.update(line)

    return digest.hexdigest()


def main() -> int:
    entries: list[tuple[str, str]] = []

    for path in files_to_hash():
        relative = str(
            path.relative_to(ROOT)
        ).replace("\\", "/")

        entries.append(
            (
                relative,
                hash_file(path),
            )
        )

    release_digest = compute_release_digest(entries)

    manifest = {
        "schema": "aura.release-lock.v2",
        "version": "1.0.0-final",
        "status": "production-locked",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "algorithm": "SHA-256",
        "release_digest": f"sha256:{release_digest}",
        "file_count": len(entries),
        "files": [
            {
                "path": relative,
                "sha256": digest,
            }
            for relative, digest in entries
        ],
        "governance": "JAS-Framework",
    }

    output = ROOT / "release-manifest.final.json"

    output.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        "AURA release lock generated:"
    )
    print(output)
    print(
        f"release_digest=sha256:{release_digest}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())