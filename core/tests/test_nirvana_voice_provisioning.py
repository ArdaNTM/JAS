"""Model installer is offline-testable and rejects bad archives."""
import io
import tarfile
from pathlib import Path

import pytest


def _load_installer():
    import importlib.util
    script = Path(__file__).resolve().parents[1] / "scripts" / "install_nirvana_voice_models.py"
    spec = importlib.util.spec_from_file_location("aura_voice_installer", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provisioning_archive_rejects_symlink(tmp_path):
    install = _load_installer()
    archive = tmp_path / "bad.tar.bz2"
    with tarfile.open(archive, "w:bz2") as t:
        member = tarfile.TarInfo("models/link.onnx")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../sensitive"
        t.addfile(member)
    with pytest.raises(RuntimeError, match="links or devices"):
        install.unpack_safe(archive, tmp_path / "output")


def test_provisioning_uses_bounded_pinned_kokoro_hashes():
    install = _load_installer()
    sources = {name: (url, size, checksum)
               for name, url, size, checksum in install.ASSETS}
    assert sources["kws"][2] is None
    assert sources["asr"][2] is None
    assert len(sources["kokoro"][2]) == 64
    assert len(sources["voices"][2]) == 64
    assert all(url.startswith("https://github.com/") for url, _, _ in sources.values())
