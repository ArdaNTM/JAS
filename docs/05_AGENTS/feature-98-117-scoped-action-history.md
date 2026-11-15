# Features #98 and #117 — scoped explainable action observations

This PR introduces `action_history.py` as a read-only projection of the
existing `KernelEvent` messages published by `SwarmOrchestrator`.
It recognizes `SwarmStepRequested`/`SwarmStepCompleted` from
`aura.swarm` for an **exact principal/task scope** and produces bounded
observations and a deterministic redacted Markdown summary. It never reads
or reports raw tool arguments, event payloads, principal IDs, task IDs,
secrets, request bodies or untrusted free-form metadata.

**A completed event means a Gateway response was observed, NOT that
external tool work succeeded, was independently validated, or obtained
Owner approval.** A request without response remains incomplete; allow,
deny, defer, and require-approval are *reported decisions*, not a new
authorization. Events lack signatures and are explicitly untrusted.

The function accepts only existing KernelEvents, at most 512 records and
32 possible step indices; a malformed/duplicate scoped event fails closed.
This module does not start a consumer, subscribe to the EventBus, send a
report, schedule recurring delivery, grant permission or change tool
execution. The upstream authenticated collector must enforce exact scope
and retention. No identity data are returned to a UI.

Features #98 (explainable action history) and #117 (automatic reporting)
remain PARTIAL. A real signed audit/provenance stream, principal-scoped
storage, Owner visibility, independent execution receipts, scheduled
opt-in delivery, and end-to-end acceptance are missing.

Tests include integration with the actual SwarmOrchestrator+EventBus
through a fake Gateway, DENY/REQUIRE_APPROVAL, incomplete responses,
malformed events, scope isolation and secret non-disclosure.
Run `cd core && uv run pytest -q tests/test_action_history_report.py`,
full Core Assurance and Final Release Lock.
