"""Feature #30: diagnostic evidence is read-only and metadata-only."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aura_core.kernel.diagnostics import (
    DiagnosticFinding, DiagnosticSnapshot, DiagnosticsService,
)


def sample(*, auth=0, unhealthy=False, missing=True, unavailable=False):
    return DiagnosticSnapshot(
        generated_at=datetime.now(UTC),
        configuration={
            "runtime": "local",
            "backend_endpoint": "https://private-token@example.invalid",
        },
        services=({"service_id": "private-service"},),
        capabilities=({
            "capability_id": "private-capability", "provider_id": "private-provider",
            "available": not unavailable, "healthy": not unavailable,
        },),
        health=(
            ({"service_id": "private-service", "state": (
                "unhealthy" if unhealthy else "healthy"
            )},) if not missing else ()
        ),
        authorization={"deny_total": auth},
        events={"secret": 999},
        warnings=("secret:never-output",),
    )


def test_diagnostic_findings_do_not_expose_identifiers_or_config():
    output = DiagnosticsService.diagnose(sample(auth=2, unavailable=True))
    assert [f.code for f in output] == [
        "missing_health_reports", "unavailable_capabilities",
        "authorization_denials_observed",
    ]
    assert all(f.can_execute is False and not f.authorization_checked for f in output)
    assert [f.affected_count for f in output] == [1, 1, 2]
    assert "private" not in repr(output)
    assert "secret" not in repr(output)
    assert "token" not in repr(output)


def test_healthy_snapshot_never_claims_production_attestation():
    assert DiagnosticsService.diagnose(sample(missing=False)) == ()


def test_unhealthy_reports_counted_without_double_counting():
    result = DiagnosticsService.diagnose(sample(missing=False, unhealthy=True))
    assert len(result) == 1
    assert result[0].code == "unhealthy_services"
    assert result[0].severity == "warning"
    assert result[0].affected_count == 1


def test_analyze_is_repeatable_and_does_not_mutate_snapshot():
    snapshot = sample(auth=1, missing=False)
    prior = repr(snapshot)
    assert DiagnosticsService.diagnose(snapshot) == DiagnosticsService.diagnose(snapshot)
    assert repr(snapshot) == prior


@pytest.mark.parametrize("invalid", [None, object(), {"deny_total": 1}])
def test_rejects_non_snapshots(invalid):
    with pytest.raises(ValueError):
        DiagnosticsService.diagnose(invalid)


@pytest.mark.parametrize("invalid", [-1, True, "1", 1.0])
def test_rejects_type_confused_denial_counts(invalid):
    with pytest.raises(ValueError):
        DiagnosticsService.diagnose(sample(auth=invalid))
