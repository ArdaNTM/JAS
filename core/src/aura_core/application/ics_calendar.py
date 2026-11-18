"""Read-only, bounded iCalendar VEVENT view of already-authorized text.

Never fetch calendars, invite attendees, create events, or call MCP providers.
Only explicit UTC times and all-day dates are supported; recurrence/timezone
rules fail closed instead of silently displaying a misleading schedule.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

_SOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    event_id: str
    summary: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool
    untrusted: bool = True


@dataclass(frozen=True, slots=True)
class CalendarSnapshot:
    source_id: str
    content_sha256: str
    events: tuple[CalendarEvent, ...]
    untrusted: bool = True
    authorization_checked: bool = False
    calendar_verified: bool = False


def _unfold(text: str) -> list[str]:
    if type(text) is not str:
        raise ValueError("calendar text must be a string")
    try:
        binary = text.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("invalid calendar encoding") from exc
    if not 1 <= len(binary) <= 262144 or "\x00" in text:
        raise ValueError("calendar text exceeds size budget")
    normalized = text.replace("\r\n", "\n")
    if "\r" in normalized:
        raise ValueError("standalone carriage return unsupported")
    lines: list[str] = []
    for line in normalized.split("\n"):
        if not line:
            continue
        if line.startswith((" ", "\t")):
            if not lines:
                raise ValueError("invalid iCalendar folded line")
            lines[-1] += line[1:]
        else:
            lines.append(line)
        if len(lines) > 10000 or len(lines[-1]) > 4096:
            raise ValueError("calendar line budget exceeded")
    return lines


def _utc(value: str, date_only: bool) -> datetime:
    try:
        if date_only:
            if not re.fullmatch(r"[0-9]{8}", value):
                raise ValueError("invalid all-day date")
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)
        if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", value):
            raise ValueError("UTC calendar timestamps required")
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except (ValueError, OverflowError) as exc:
        raise ValueError("invalid or unsupported calendar timestamp") from exc


def _event(data: dict[str, str]) -> CalendarEvent:
    if not all(key in data for key in ("UID", "SUMMARY", "DTSTART", "DTEND")):
        raise ValueError("incomplete calendar event")
    uid = data["UID"]
    if not 1 <= len(uid) <= 256 or any(ord(ch) < 32 for ch in uid):
        raise ValueError("invalid calendar event UID")
    summary = (
        data["SUMMARY"]
        .replace("\\n", " ").replace("\\N", " ")
        .replace("\\,", ",").replace("\\;", ";")
        .replace("\\\\", "\\")
    )
    if not 1 <= len(summary.strip()) <= 250 or any(ord(ch) < 32 for ch in summary):
        raise ValueError("invalid event summary")
    start_day = data.get("START_DATE_ONLY") == "yes"
    end_day = data.get("END_DATE_ONLY") == "yes"
    if start_day != end_day:
        raise ValueError("calendar start/end date kinds mismatch")
    start = _utc(data["DTSTART"], start_day)
    end = _utc(data["DTEND"], end_day)
    if end <= start or end - start > timedelta(days=366):
        raise ValueError("invalid event duration")
    return CalendarEvent(
        event_id=hashlib.sha256(uid.encode("utf-8")).hexdigest(),
        summary=summary.strip(), starts_at=start, ends_at=end,
        all_day=start_day,
    )


def parse_ics_calendar(
    text: str, *, source_id: str, max_events: int = 200
) -> CalendarSnapshot:
    """Parse bounded VEVENT records without evaluating or dispatching actions."""
    if type(source_id) is not str or not _SOURCE_ID.fullmatch(source_id):
        raise ValueError("invalid calendar source identity")
    if type(max_events) is not int or not 1 <= max_events <= 200:
        raise ValueError("max_events must be 1..200")
    lines = _unfold(text)
    if len(lines) < 3 or lines[0] != "BEGIN:VCALENDAR" or lines[-1] != "END:VCALENDAR":
        raise ValueError("invalid VCALENDAR envelope")
    current: dict[str, str] | None = None
    seen: dict[str, CalendarEvent] = {}
    version_found = False
    for line in lines[1:-1]:
        if line == "BEGIN:VEVENT":
            if current is not None:
                raise ValueError("nested calendar event unsupported")
            current = {}
            continue
        if line == "END:VEVENT":
            if current is None:
                raise ValueError("unmatched event end")
            event = _event(current)
            if event.event_id in seen and seen[event.event_id] != event:
                raise ValueError("ambiguous duplicate event UID")
            seen[event.event_id] = event
            if len(seen) > max_events:
                raise ValueError("calendar event count exceeded")
            current = None
            continue
        if line.startswith(("BEGIN:", "END:")):
            raise ValueError("nested/non-event calendar components unsupported")
        if ":" not in line:
            raise ValueError("invalid calendar property")
        field, value = line.split(":", 1)
        property_name = field.upper().split(";", 1)[0]
        if current is None:
            if property_name == "VERSION":
                if version_found or value != "2.0":
                    raise ValueError("invalid iCalendar version")
                version_found = True
            continue
        if property_name in {
            "RRULE", "RDATE", "EXDATE", "RECURRENCE-ID",
            "ATTACH", "URL", "TRIGGER",
        }:
            raise ValueError("unsupported recurring or external calendar field")
        if property_name in {"UID", "SUMMARY", "DTSTART", "DTEND"}:
            if property_name in current:
                raise ValueError("duplicate required calendar property")
            if property_name in {"DTSTART", "DTEND"}:
                if field.upper() not in {
                    property_name, property_name + ";VALUE=DATE",
                }:
                    raise ValueError("timezone-specific or unsupported event timestamp")
                if field.upper().endswith(";VALUE=DATE"):
                    current["START_DATE_ONLY" if property_name == "DTSTART" else "END_DATE_ONLY"] = "yes"
            current[property_name] = value
    if current is not None or not version_found:
        raise ValueError("unterminated event or calendar version missing")
    events = tuple(sorted(seen.values(), key=lambda e: (e.starts_at, e.event_id)))
    return CalendarSnapshot(
        source_id=source_id,
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        events=events,
    )


def events_between(
    snapshot: CalendarSnapshot, *, start: datetime, end: datetime,
    limit: int = 20,
) -> tuple[CalendarEvent, ...]:
    """Select overlapping events within an explicit UTC-aware query window."""
    if type(snapshot) is not CalendarSnapshot:
        raise ValueError("CalendarSnapshot required")
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("limit must be 1..50")
    for value in (start, end):
        if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone-aware query bounds required")
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    if start >= end or end - start > timedelta(days=366):
        raise ValueError("invalid calendar time window")
    return tuple(
        event for event in snapshot.events
        if event.starts_at < end and event.ends_at > start
    )[:limit]
