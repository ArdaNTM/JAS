import json

import pytest

from aura_core.enterprise.policy_bundle import PolicyBundle, PolicyEffect


def test_policy_bundle_loads_strict_json_file_and_computes_digest(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({
        "version": "2026.10.1",
        "rules": [{
            "rule_id": "read-workspace",
            "principal_id": "local_owner",
            "capability_id": "filesystem.read",
            "operation_id": "filesystem.read_file",
            "resource_scope": "workspace:main",
            "effect": "allow",
            "priority": 10,
        }],
    }), encoding="utf-8")

    bundle = PolicyBundle.from_json_file(path)

    assert bundle.version == "2026.10.1"
    assert bundle.rules[0].effect is PolicyEffect.ALLOW
    assert len(bundle.digest) == 64


@pytest.mark.parametrize(
    "payload",
    [
        {"version": "v1", "rules": [], "unexpected": True},
        {"version": "v1", "rules": [{"rule_id": "r1"}]},
        {"version": "v1", "rules": [{
            "rule_id": "r1",
            "principal_id": "local_owner",
            "capability_id": "filesystem.read",
            "operation_id": "read",
            "resource_scope": "workspace:main",
            "effect": "maybe",
        }]},
    ],
)
def test_policy_bundle_loader_rejects_invalid_schema_or_values(tmp_path, payload):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        PolicyBundle.from_json_file(path)


def test_policy_bundle_loader_fails_closed_for_missing_file(tmp_path):
    with pytest.raises(ValueError, match="Unable to load policy bundle JSON"):
        PolicyBundle.from_json_file(tmp_path / "missing.json")

def test_policy_bundle_loader_accepts_utf8_bom_json(tmp_path):
    path = tmp_path / "policy-bundle.json"
    payload = {
        "version": "bom-test-v1",
        "rules": [{
            "rule_id": "allow-test-read",
            "principal_id": "local-user",
            "capability_id": "filesystem.read_test_data",
            "operation_id": "filesystem.read_test_data",
            "resource_scope": r"D:\\AURA\\workspace",
            "effect": "allow",
        }],
    }
    path.write_bytes(b"\\xef\\xbb\\xbf" + json.dumps(payload).encode("utf-8"))

    bundle = PolicyBundle.from_json_file(path)

    assert bundle.version == "bom-test-v1"
    assert len(bundle.rules) == 1
    assert bundle.rules[0].effect is PolicyEffect.ALLOW

