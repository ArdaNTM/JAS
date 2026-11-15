# Feature 029 — advisory disk pressure telemetry

Status: partial implementation and review candidate, pending CI and real-host acceptance.

Existing `SystemTelemetry` reports optional best-effort CPU, RAM, and network counters. This change adds `disk_percent` and `disk_free_bytes` for a configurable path (default user home) via the existing optional `psutil` adapter. The `disk_warning` threshold defaults to 90%.

The sample is **read-only** and *advisory*. A disk-pressure alert recommends manual review and never deletes files, changes permissions, invokes the MCP Gateway or modifies privileged state. Invalid or unreadable disk samples produce `None` disk fields while preserving other metrics; the private filesystem path and exception details are not returned.

This is not a hardware-verified temperature/GPU monitoring solution. It is host telemetry under the existing JAS architecture, not an authorization mechanism. Additional provider-specific hardware probes, UI/dashboard integration and physical machine acceptance remain separate work.

Tests: `cd core && uv run pytest -q tests/test_disk_health_telemetry.py`; full AURA Core Assurance and deterministic release-lock verification are required. No new dependencies or external API calls.
