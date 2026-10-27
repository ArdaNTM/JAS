from __future__ import annotations

import pytest

from aura_core.main import build_app


@pytest.mark.parametrize("invalid_kind", ["missing", "malformed", "directory"])
def test_configured_invalid_policy_bundle_fails_closed_before_app_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    invalid_kind: str,
) -> None:
    if invalid_kind == "missing":
        policy_path = tmp_path / "does-not-exist.json"
    elif invalid_kind == "malformed":
        policy_path = tmp_path / "policy.json"
        policy_path.write_text('{"version": ', encoding="utf-8")
    else:
        policy_path = tmp_path / "policy-directory"
        policy_path.mkdir()

    monkeypatch.setenv("AURA_POLICY_BUNDLE_PATH", str(policy_path))

    # A configured but invalid bundle must stop composition rather than silently
    # starting with legacy-only authorization. build_app loads the bundle before
    # bootstrapping the kernel or exposing any provider.
    with pytest.raises(ValueError):
        build_app()
