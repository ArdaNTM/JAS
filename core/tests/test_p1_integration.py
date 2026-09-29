from pathlib import Path
import hashlib

JAS_SNAPSHOT = Path(r"D:\AURA\JAS\acquisition\host_snapshot\host_snapshot.txt")

def test_jas_host_snapshot_exists():
    assert JAS_SNAPSHOT.is_file()
    assert JAS_SNAPSHOT.stat().st_size > 0

def test_jas_host_snapshot_sha256():
    expected = "5D8B7E52CBA17D02CEDD417A4E07CC1F5F2270172BDE5D5E5FE53084E85C3F9F"
    digest = hashlib.sha256(JAS_SNAPSHOT.read_bytes()).hexdigest().upper()
    assert digest == expected
