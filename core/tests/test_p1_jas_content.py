from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JAS_SNAPSHOT = REPO_ROOT / "acquisition" / "host_snapshot" / "host_snapshot.txt"


def test_jas_snapshot_contains_required_sections():
    content = JAS_SNAPSHOT.read_text(encoding="utf-16")

    for section in ("=== OS ===", "=== CPU / RAM ===", "=== NVIDIA ===", "=== PYTHON ===", "=== OLLAMA ===", "=== GIT ==="):
        assert section in content
