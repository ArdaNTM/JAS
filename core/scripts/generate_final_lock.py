from __future__ import annotations
import hashlib
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]

def get_git_commit() -> str:
    try:
        return subprocess.check_output("git rev-parse HEAD", cwd=ROOT, shell=True, text=True).strip()
    except Exception:
        return "unversioned_working_tree"

def compute_dir_hash(directory: Path) -> str:
    sha256 = hashlib.sha256()
    for path in sorted(directory.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        sha256.update(path.read_bytes())
    return sha256.hexdigest()

def main() -> None:
    core_src = ROOT / "core" / "src" / "aura_core"
    core_hash = compute_dir_hash(core_src) if core_src.exists() else "unknown"

    manifest = {
        "version": "1.0.0-final",
        "status": "production-locked",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commit": get_git_commit(),
        "core_digest": f"sha256:{core_hash}",
        "governance": "JAS-Framework",
        "capabilities": [
            "Deterministic Kernel", "Permission Engine", "MCP Gateway",
            "WebSocket Live Hub", "Multi-Provider LLM Router", "Sandbox File/Browser"
        ]
    }
    
    out_path = ROOT / "release-manifest.final.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"🔒 Gerçek SHA-256 Digest ile Mühürlenmiş Manifest Üretildi: {out_path}")

if __name__ == "__main__":
    main()
