from pathlib import Path

JAS_SNAPSHOT = Path(r"D:\AURA\JAS\acquisition\host_snapshot\host_snapshot.txt")


def test_jas_snapshot_contains_required_sections():
    content = JAS_SNAPSHOT.read_text(encoding="utf-16")

    for section in ("=== OS ===", "=== CPU / RAM ===", "=== NVIDIA ===", "=== PYTHON ===", "=== OLLAMA ===", "=== GIT ==="):
        assert section in content
