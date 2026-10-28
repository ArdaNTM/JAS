from __future__ import annotations

import json

import pytest

from aura_core.enterprise.policy_bundle import PolicyBundle
from aura_core.main import _load_policy_bundle_from_environment


def _write_bundle(path):
    path.write_text(
        json.dumps(
            {
                "version": "integrity-test-v1",
                "rules": [
                    {
                        "rule_id": "read-test-data",
                        "principal_id": "local_owner",
                        "capability_id": "filesystem.read_test_data",
                        "operation_id": "filesystem.read_test_data",
                        "resource_scope": "local_default",
                        "effect": "allow",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return PolicyBundle.from_json_file(path)


def test_policy_bundle_digest_pin_accepts_matching_digest(tmp_path, monkeypatch):
    path = tmp_path / "policy.json"
    expected = _write_bundle(path).digest
    monkeypatch.setenv("AURA_POLICY_BUNDLE_PATH", str(path))
    monkeypatch.setenv("AURA_POLICY_BUNDLE_SHA256", expected.upper())

    loaded = _load_policy_bundle_from_environment()

    assert loaded is not None
    assert loaded.digest == expected


def test_policy_bundle_digest_pin_rejects_modified_policy(tmp_path, monkeypatch):
    path = tmp_path / "policy.json"
    _write_bundle(path)
    monkeypatch.setenv("AURA_POLICY_BUNDLE_PATH", str(path))
    monkeypatch.setenv("AURA_POLICY_BUNDLE_SHA256", "0" * 64)

    with pytest.raises(ValueError, match="does not match"):
        _load_policy_bundle_from_environment()


@pytest.mark.parametrize("invalid_digest", ["not-a-digest", "a" * 63, "g" * 64])
def test_policy_bundle_digest_pin_rejects_malformed_digest(
    tmp_path, monkeypatch, invalid_digest
):
    path = tmp_path / "policy.json"
    _write_bundle(path)
    monkeypatch.setenv("AURA_POLICY_BUNDLE_PATH", str(path))
    monkeypatch.setenv("AURA_POLICY_BUNDLE_SHA256", invalid_digest)

    with pytest.raises(ValueError, match="64-character hexadecimal"):
        _load_policy_bundle_from_environment()


def test_policy_bundle_digest_pin_requires_bundle_path(monkeypatch):
    monkeypatch.delenv("AURA_POLICY_BUNDLE_PATH", raising=False)
    monkeypatch.setenv("AURA_POLICY_BUNDLE_SHA256", "a" * 64)

    with pytest.raises(ValueError, match="requires AURA_POLICY_BUNDLE_PATH"):
        _load_policy_bundle_from_environment()


def test_policy_bundle_without_digest_pin_remains_compatible(tmp_path, monkeypatch):
    path = tmp_path / "policy.json"
    expected = _write_bundle(path).digest
    monkeypatch.setenv("AURA_POLICY_BUNDLE_PATH", str(path))
    monkeypatch.delenv("AURA_POLICY_BUNDLE_SHA256", raising=False)

    loaded = _load_policy_bundle_from_environment()

    assert loaded is not None
    assert loaded.digest == expected
