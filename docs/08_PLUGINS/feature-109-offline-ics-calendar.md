# Feature #109 — offline iCalendar read-only schedule (partial)

`aura_core.application.ics_calendar` parses **already-authorized**
RFC5545-style VEVENT input without contacting the provider, dispatching
MCP tools, creating calendar events or scheduling reminders. This is a
read-only normalization and explicit time-window query primitive,
not a calendar connector.

Supported: VCALENDAR VERSION:2.0, VEVENT UID/SUMMARY, UTC DTSTART/DTEND,
all-day VALUE=DATE events, folded ICS lines, deterministic sorting and
bounded event-window selection. UIDs are SHA-256-fingerprinted in output.
Unsupported recurring events (RRULE/RDATE/EXDATE/RECURRENCE-ID),
timezone-specific timestamps, nested VALARM, ATTACH and external URL
references **fail closed** instead of silently returning an incomplete
schedule. UTC/all-day semantics are stated and not guessed from local time.

Guards: ≤256 KiB input, ≤10k unfolded lines, ≤200 events, timezone-aware
query windows ≤366 days and ≤50 returned events. All textual content is
untrusted, provider/authentication is not verified, and no persistence or
notification is performed. Actual account authentication, app approvals,
privacy controls and calendar mutations require existing Kernel,
PermissionEngine and MCP Gateway plus end-to-end review.

This supports only a subset of feature #109. No OAuth, recurring event
expansion, timezone resolver, real provider integration or booking actions.

Tests: `cd core && uv run pytest -q tests/test_offline_ics_calendar.py`.
Full AURA Core Assurance and Final Release Lock also required.
