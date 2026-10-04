from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "release-manifest.final.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def main() -> int:
    if not MANIFEST.is_file():
        print("FAIL: release-manifest.final.json missing")
        return 1

    manifest = json.loads(
        MANIFEST.read_text(
            encoding="utf-8"
        )
    )

    if manifest.get("algorithm") != "SHA-256":
        print("FAIL: invalid hash algorithm")
        return 1

    expected_release = manifest.get(
        "release_digest"
    )

    files = manifest.get("files")

    if not isinstance(files, list) or not files:
        print("FAIL: manifest has no file identities")
        return 1

    entries: list[tuple[str, str]] = []

    for item in files:
        relative = item["path"]
        expected = item["sha256"]

        path = ROOT / relative

        if not path.is_file():
            print(
                f"FAIL: missing locked file: {relative}"
            )
            return 1

        actual = sha256(path)

        if actual != expected:
            print(
                f"FAIL: digest mismatch: {relative}"
            )
            print(f" expected={expected}")
            print(f" actual={actual}")
            return 1

        entries.append(
            (relative, actual)
        )

    digest = hashlib.sha256()

    for relative, file_digest in sorted(
        entries,
        key=lambda value: value[0].lower(),
    ):
        digest.update(
            f"{relative}\t{file_digest}\n".encode(
                "utf-8"
            )
        )

    actual_release = (
        "sha256:"
        + digest.hexdigest()
    )

    if actual_release != expected_release:
        print("FAIL: release digest mismatch")
        print(f" expected={expected_release}")
        print(f" actual={actual_release}")
        return 1

    print(
        "AURA FINAL RELEASE LOCK: PASS"
    )
    print(
        f"release_digest={actual_release}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())