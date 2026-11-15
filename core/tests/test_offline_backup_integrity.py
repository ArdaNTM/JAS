"""Feature #105: corruption detection and no-write backup envelope tests."""
from __future__ import annotations

import io
import json
import stat
import zipfile

import pytest

from aura_core.persistence.offline_backup import (
    make_backup_bundle, verify_backup_bundle,
)


def rewrite(bundle, *, changed=None, add=None):
    source = io.BytesIO(bundle)
    result = io.BytesIO()
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(result, "w") as out:
        for item in original.infolist():
            content = original.read(item.filename)
            if changed and item.filename in changed:
                content = changed[item.filename]
            out.writestr(item, content)
        if add:
            for path, content in add.items():
                out.writestr(path, content)
    return result.getvalue()


def test_roundtrip_is_reproducible_and_verifies_real_bytes(tmp_path):
    files = {"notes/hello.txt": "Merhaba".encode(), "state.json": b"{}"}
    one = make_backup_bundle(files, principal_id="owner:123")
    two = make_backup_bundle(dict(reversed(list(files.items()))), principal_id="owner:123")
    assert one == two
    verified = verify_backup_bundle(one, principal_id="owner:123")
    assert [row.path for row in verified.entries] == ["notes/hello.txt", "state.json"]
    assert verified.checksums_verified
    assert not verified.authenticity_verified
    assert not verified.encrypted
    assert not verified.authorization_checked
    assert not verified.restored
    assert not list(tmp_path.iterdir())


def test_wrong_principal_and_modified_content_fail_closed():
    blob = make_backup_bundle({"private.txt": b"original"}, principal_id="alice")
    with pytest.raises(PermissionError):
        verify_backup_bundle(blob, principal_id="bob")
    modified = rewrite(blob, changed={"private.txt": b"tampered"})
    with pytest.raises(ValueError, match="integrity mismatch"):
        verify_backup_bundle(modified, principal_id="alice")


def test_unrecorded_added_member_is_rejected():
    blob = make_backup_bundle({"note.txt": b"x"}, principal_id="owner")
    modified = rewrite(blob, add={"hidden.txt": b"secret"})
    with pytest.raises(ValueError, match="unrecorded"):
        verify_backup_bundle(modified, principal_id="owner")


@pytest.mark.parametrize("path", [
    "../secrets", "/absolute/path", r"folder\file.txt", "C:drive.txt",
    "path/./item", "path//item", "folder/..", "trailing./file",
])
def test_unsafe_backup_file_paths_rejected(path):
    with pytest.raises(ValueError):
        make_backup_bundle({path: b"x"}, principal_id="owner")


def test_casefold_collision_and_reserved_manifest_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        make_backup_bundle({"A.txt": b"a", "a.TXT": b"b"}, principal_id="owner")
    with pytest.raises(ValueError):
        make_backup_bundle({"manifest.json": b"inject"}, principal_id="owner")


def test_bounded_bytes_types_and_counts():
    with pytest.raises(ValueError):
        make_backup_bundle({}, principal_id="owner")
    with pytest.raises(ValueError):
        make_backup_bundle({"a": bytearray(b"private")}, principal_id="owner")
    with pytest.raises(ValueError):
        make_backup_bundle({"a": b"x" * (2 * 1024 * 1024 + 1)}, principal_id="owner")
    with pytest.raises(ValueError):
        make_backup_bundle({str(n): b"x" for n in range(51)}, principal_id="owner")
    with pytest.raises(ValueError):
        make_backup_bundle({"a": b"x"}, principal_id="../owner")
    with pytest.raises(ValueError):
        verify_backup_bundle("path/to/file.zip", principal_id="owner")


def test_traversal_and_symlink_members_refused_on_verification():
    blob = make_backup_bundle({"safe.txt": b"x"}, principal_id="owner")
    with pytest.raises(ValueError, match="unsafe"):
        verify_backup_bundle(
            rewrite(blob, add={"../outside": b"bad"}), principal_id="owner"
        )
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        with zipfile.ZipFile(io.BytesIO(blob), "r") as original:
            for item in original.infolist():
                archive.writestr(item, original.read(item.filename))
        symlink = zipfile.ZipInfo("link")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(symlink, "elsewhere")
    with pytest.raises(ValueError, match="links"):
        verify_backup_bundle(result.getvalue(), principal_id="owner")


def test_untrusted_manifest_schema_and_compression_denied():
    blob = make_backup_bundle({"note.txt": b"x"}, principal_id="owner")
    tampered = rewrite(blob, changed={"manifest.json": json.dumps({"schema": "wrong"}).encode()})
    with pytest.raises(ValueError, match="schema"):
        verify_backup_bundle(tampered, principal_id="owner")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        with zipfile.ZipFile(io.BytesIO(blob)) as original:
            for item in original.infolist():
                archive.writestr(item.filename, original.read(item.filename))
    with pytest.raises(ValueError, match="compressed"):
        verify_backup_bundle(out.getvalue(), principal_id="owner")


def test_checksum_is_not_signature_or_owner_receipt():
    bundle = make_backup_bundle({"settings": b"data"}, principal_id="alice")
    result = verify_backup_bundle(bundle, principal_id="alice")
    assert result.authenticity_verified is False
    assert result.authorization_checked is False
    assert result.restored is False
