"""Feature #109: parse already-authorized ICS without executing invitations."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aura_core.application.ics_calendar import (
    events_between, parse_ics_calendar,
)


def ics(*events):
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", *events, "END:VCALENDAR", ""])


def event(uid="one", summary="Review", start="20261115T120000Z", end="20261115T130000Z"):
    return "\r\n".join([
        "BEGIN:VEVENT", "UID:" + uid, "SUMMARY:" + summary,
        "DTSTART:" + start, "DTEND:" + end, "END:VEVENT",
    ])


def test_real_utc_events_and_time_window_selection():
    text = ics(
        event("later", "Later", "20261116T120000Z", "20261116T140000Z"),
        event("earlier", "Meeting", "20261115T120000Z", "20261115T130000Z"),
    )
    snapshot = parse_ics_calendar(text, source_id="offline-cal")
    assert [x.summary for x in snapshot.events] == ["Meeting", "Later"]
    assert all(x.untrusted for x in snapshot.events)
    assert not snapshot.authorization_checked and not snapshot.calendar_verified
    start = datetime(2026, 11, 15, 12, tzinfo=UTC)
    result = events_between(snapshot, start=start, end=start + timedelta(hours=1))
    assert [x.summary for x in result] == ["Meeting"]
    assert len(snapshot.events[0].event_id) == 64


def test_folded_lines_and_all_day_events():
    all_day = "\r\n".join([
        "BEGIN:VEVENT", "UID:day1", "SUMMARY:Vacation ",
        " continuation", "DTSTART;VALUE=DATE:20261115",
        "DTEND;VALUE=DATE:20261117", "END:VEVENT",
    ])
    snapshot = parse_ics_calendar(ics(all_day), source_id="holidays")
    assert snapshot.events[0].all_day
    assert snapshot.events[0].summary == "Vacation continuation"
    assert snapshot.events[0].ends_at - snapshot.events[0].starts_at == timedelta(days=2)


def test_same_uid_conflict_fails_closed():
    with pytest.raises(ValueError, match="ambiguous duplicate"):
        parse_ics_calendar(
            ics(event("same", "A"), event("same", "B")), source_id="my-calendar",
        )


@pytest.mark.parametrize("bad_event", [
    "BEGIN:VEVENT\r\nUID:r\r\nRRULE:FREQ=DAILY\r\nSUMMARY:Repeat\r\nDTSTART:20261115T120000Z\r\nDTEND:20261115T130000Z\r\nEND:VEVENT",
    "BEGIN:VEVENT\r\nUID:r\r\nSUMMARY:External\r\nATTACH:https://example.org/file\r\nDTSTART:20261115T120000Z\r\nDTEND:20261115T130000Z\r\nEND:VEVENT",
    "BEGIN:VEVENT\r\nUID:r\r\nSUMMARY:Alarm\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nEND:VALARM\r\nDTSTART:20261115T120000Z\r\nDTEND:20261115T130000Z\r\nEND:VEVENT",
    event(start="20261115T130000Z", end="20261115T120000Z"),
    event(start="20261115T120000", end="20261115T130000Z"),
    "BEGIN:VEVENT\r\nUID:r\r\nSUMMARY:No end\r\nDTSTART:20261115T120000Z\r\nEND:VEVENT",
    "BEGIN:VEVENT\r\nUID:r\r\nSUMMARY:Timezone\r\nDTSTART;TZID=Europe/Berlin:20261115T120000\r\nDTEND:20261115T130000Z\r\nEND:VEVENT",
])
def test_recurring_external_bad_duration_and_missing_fields_rejected(bad_event):
    with pytest.raises(ValueError):
        parse_ics_calendar(ics(bad_event), source_id="offline-cal")


def test_malformed_envelope_versions_and_calendar_source():
    for payload in ("BEGIN:VCALENDAR\r\nEND:VCALENDAR", "not calendar", ics(event()).replace("VERSION:2.0", "VERSION:1.0")):
        with pytest.raises(ValueError):
            parse_ics_calendar(payload, source_id="offline-cal")
    with pytest.raises(ValueError):
        parse_ics_calendar(ics(event()), source_id="../secret")


def test_duplicate_property_and_control_character_rejected():
    duplicate = event().replace("SUMMARY:Review", "SUMMARY:A\r\nSUMMARY:B")
    with pytest.raises(ValueError):
        parse_ics_calendar(ics(duplicate), source_id="offline-cal")
    with pytest.raises(ValueError):
        parse_ics_calendar(ics(event(summary="A\x00B")), source_id="offline-cal")


def test_bounds_and_query_fail_closed():
    source = ics(event())
    with pytest.raises(ValueError):
        parse_ics_calendar(source, source_id="offline", max_events=False)
    with pytest.raises(ValueError):
        parse_ics_calendar(ics(event("a"), event("b")), source_id="offline", max_events=1)
    with pytest.raises(ValueError):
        parse_ics_calendar("x" * 262145, source_id="offline")
    snap = parse_ics_calendar(source, source_id="offline")
    start = datetime(2026, 11, 15, 11, tzinfo=UTC)
    with pytest.raises(ValueError):
        events_between(snap, start=start, end=start + timedelta(hours=1), limit=True)
    with pytest.raises(ValueError):
        events_between(snap, start=start.replace(tzinfo=None), end=start + timedelta(hours=1))
    with pytest.raises(ValueError):
        events_between(snap, start=start, end=start + timedelta(days=367))
