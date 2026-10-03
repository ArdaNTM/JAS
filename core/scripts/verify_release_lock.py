"""Release gate: validates immutable identities without mutating lock artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "core" / "release-manifest.json"
REQUIRED = (ROOT / "core" / "uv.lock", ROOT / "aura-ui" / "package-lock.json")


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED if not path.is_file()]
    if missing:
        print("release lock blocked: missing " + ", ".join(missing))
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    if not manifest.get("version") or not manifest.get("components"):
        print("release lock blocked: release manifest lacks immutable version metadata")
        return 1
    for path in REQUIRED:
        print(f"{path.relative_to(ROOT)} sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}")
    print("release lock input validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
