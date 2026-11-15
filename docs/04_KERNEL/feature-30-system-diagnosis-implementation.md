# Feature #30 — non-executing system diagnosis

Scope: partial JAS extension to existing `DiagnosticsService`, not a new
Kernel, tool provider or operating-system agent.

`DiagnosticsService.diagnose(snapshot)` accepts an existing
`DiagnosticSnapshot` and produces fixed, metadata-only findings for:
missing health reports, unhealthy services, unavailable capabilities, and
observed authorization denials. It never publishes events, reads host logs,
executes tools, restarts services, changes permissions, returns raw IDs,
configuration URLs, credentials or audit payloads.

`DiagnosticFinding.can_execute=False` and
`authorization_checked=False` explicitly signal that this result does not
confer action authority. Actual remediation must remain Owner-authorized
through the existing PermissionEngine and MCP Gateway.

Tests cover aggregate detection, no disclosure of source values,
read-only repeatability, invalid snapshot/denial values and healthy cases.
The implementation is a diagnostic classification primitive, not a complete
operating-system troubleshooting workflow. A successful empty finding list
is not proof of comprehensive system security or production readiness.

Test: `cd core && uv run pytest -q tests/test_system_diagnosis.py`
and full AURA Core Assurance/Release Lock.
