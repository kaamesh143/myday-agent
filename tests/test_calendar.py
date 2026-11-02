import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httplib2
import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

import app.calendar_source as cal
from app.calendar_source import (
    NOT_CONNECTED,
    SIGNED_OUT,
    UNAVAILABLE,
    CalendarError,
    fetch_events_today,
    find_overlaps,
    format_events,
    get_calendar_text,
)

TZ = "Europe/Stockholm"
DAY = datetime.date(2026, 11, 2)


def timed(title, start, end, **extra):
    return {"summary": title, "start": {"dateTime": start}, "end": {"dateTime": end}, **extra}


def fake_service(items_by_calendar):
    """A stand-in for the Google Calendar API. It records every list() call."""
    calls = []

    def list_(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(execute=lambda: {"items": items_by_calendar.get(kwargs["calendarId"], [])})

    return SimpleNamespace(events=lambda: SimpleNamespace(list=list_)), calls


def read(items, calendars=("primary",), private=frozenset()):
    service, _ = fake_service(items if isinstance(items, dict) else {"primary": items})
    return fetch_events_today(service, DAY, TZ, calendars, private)


def test_utc_times_are_shown_in_the_owners_timezone():
    events = read([timed("Standup", "2026-11-02T08:00:00Z", "2026-11-02T08:30:00Z")])
    assert format_events(events, DAY) == "09:00–09:30 Standup"


def test_all_day_events_come_first():
    events = read(
        [
            timed("Standup", "2026-11-02T09:00:00+01:00", "2026-11-02T09:30:00+01:00"),
            {"summary": "Public holiday", "start": {"date": "2026-11-02"}, "end": {"date": "2026-11-03"}},
        ]
    )
    assert format_events(events, DAY).splitlines() == ["All day: Public holiday", "09:00–09:30 Standup"]


def test_cancelled_and_declined_events_are_hidden():
    events = read(
        [
            timed("Cancelled", "2026-11-02T09:00:00+01:00", "2026-11-02T10:00:00+01:00", status="cancelled"),
            timed(
                "Declined",
                "2026-11-02T10:00:00+01:00",
                "2026-11-02T11:00:00+01:00",
                attendees=[{"self": True, "responseStatus": "declined"}],
            ),
            timed(
                "Accepted",
                "2026-11-02T11:00:00+01:00",
                "2026-11-02T12:00:00+01:00",
                attendees=[{"self": True, "responseStatus": "accepted"}],
            ),
        ]
    )
    assert format_events(events, DAY) == "11:00–12:00 Accepted"


def test_private_calendar_titles_are_replaced_by_busy():
    items = {
        "primary": [timed("Dentist", "2026-11-02T08:00:00+01:00", "2026-11-02T09:00:00+01:00")],
        "office": [timed("Secret merger talk", "2026-11-02T13:00:00+01:00", "2026-11-02T14:00:00+01:00")],
    }
    events = read(items, calendars=("primary", "office"), private=frozenset({"office"}))
    text = format_events(events, DAY)
    assert "Dentist" in text
    assert "13:00–14:00 Busy" in text
    assert "Secret" not in text


def test_overlap_across_calendars_is_flagged():
    items = {
        "primary": [timed("Lunch", "2026-11-02T12:00:00+01:00", "2026-11-02T13:00:00+01:00")],
        "office": [timed("Review", "2026-11-02T12:30:00+01:00", "2026-11-02T13:30:00+01:00")],
    }
    text = format_events(read(items, calendars=("primary", "office")), DAY)
    assert text.splitlines() == [
        "12:00–13:00 Lunch (overlaps with Review)",
        "12:30–13:30 Review (overlaps with Lunch)",
    ]


def test_back_to_back_events_do_not_overlap():
    events = read(
        [
            timed("A", "2026-11-02T09:00:00+01:00", "2026-11-02T10:00:00+01:00"),
            timed("B", "2026-11-02T10:00:00+01:00", "2026-11-02T11:00:00+01:00"),
        ]
    )
    assert find_overlaps(events) == {}


def test_all_day_events_never_count_as_overlaps():
    events = read(
        [
            {"summary": "Holiday", "start": {"date": "2026-11-02"}, "end": {"date": "2026-11-03"}},
            timed("A", "2026-11-02T09:00:00+01:00", "2026-11-02T10:00:00+01:00"),
        ]
    )
    assert find_overlaps(events) == {}


def test_empty_day():
    assert format_events([], DAY) == "No meetings today."


def test_only_ten_events_are_listed():
    items = [
        timed(f"E{hour}", f"2026-11-02T{hour:02d}:00:00+01:00", f"2026-11-02T{hour:02d}:30:00+01:00")
        for hour in range(8, 20)
    ]
    lines = format_events(read(items), DAY).splitlines()
    assert len(lines) == 11
    assert lines[-1] == "+2 more"


def test_long_and_missing_titles():
    events = read(
        [
            timed("x" * 200, "2026-11-02T09:00:00+01:00", "2026-11-02T10:00:00+01:00"),
            {
                "start": {"dateTime": "2026-11-02T11:00:00+01:00"},
                "end": {"dateTime": "2026-11-02T12:00:00+01:00"},
            },
        ]
    )
    lines = format_events(events, DAY).splitlines()
    assert lines[0] == "09:00–10:00 " + "x" * 80
    assert lines[1] == "11:00–12:00 (no title)"


def test_events_crossing_midnight_have_clear_labels():
    events = read(
        [
            timed("Night shift", "2026-11-01T22:00:00+01:00", "2026-11-02T02:00:00+01:00"),
            timed("Flight", "2026-11-02T22:00:00+01:00", "2026-11-03T01:00:00+01:00"),
        ]
    )
    assert format_events(events, DAY).splitlines() == ["until 02:00 Night shift", "from 22:00 Flight"]


def test_query_asks_for_the_local_day_of_every_calendar():
    service, calls = fake_service({})
    fetch_events_today(service, DAY, TZ, ("primary", "office"), frozenset())
    assert [call["calendarId"] for call in calls] == ["primary", "office"]
    assert calls[0]["timeMin"] == "2026-11-02T00:00:00+01:00"
    assert calls[0]["timeMax"] == "2026-11-03T00:00:00+01:00"
    assert calls[0]["singleEvents"] is True
    assert calls[0]["orderBy"] == "startTime"


def test_query_bounds_follow_daylight_saving_change():
    service, calls = fake_service({})
    fetch_events_today(service, datetime.date(2026, 10, 25), TZ, ("primary",), frozenset())
    assert calls[0]["timeMin"] == "2026-10-25T00:00:00+02:00"
    assert calls[0]["timeMax"] == "2026-10-26T00:00:00+01:00"


def test_malformed_event_raises_calendar_error():
    with pytest.raises(CalendarError):
        read([{"summary": "No times"}])


def get_text(tmp_path, factory, create_token=True):
    token = tmp_path / "token.json"
    if create_token:
        token.write_text("{}")
    now = datetime.datetime(2026, 11, 2, 7, 0, tzinfo=ZoneInfo(TZ))
    return get_calendar_text(token, TZ, ("primary",), service_factory=factory, now=now)


def test_missing_token_means_not_connected(tmp_path):
    def must_not_be_called(path):
        raise AssertionError("no token, so no service")

    assert get_text(tmp_path, must_not_be_called, create_token=False) == NOT_CONNECTED


def test_expired_sign_in_gets_its_own_message(tmp_path):
    def expired(path):
        raise RefreshError("invalid_grant")

    assert get_text(tmp_path, expired) == SIGNED_OUT


@pytest.mark.parametrize(
    "error",
    [HttpError(httplib2.Response({"status": 500}), b"boom"), OSError("network down")],
)
def test_other_failures_give_a_short_message(tmp_path, error):
    def failing(path):
        raise error

    assert get_text(tmp_path, failing) == UNAVAILABLE


def test_success_path_returns_formatted_events(tmp_path):
    service, _ = fake_service(
        {"primary": [timed("Standup", "2026-11-02T09:00:00+01:00", "2026-11-02T09:30:00+01:00")]}
    )
    assert get_text(tmp_path, lambda path: service) == "09:00–09:30 Standup"


def test_failures_are_logged_without_event_content(tmp_path, caplog):
    def failing(path):
        raise OSError("Secret merger talk")

    with caplog.at_level("WARNING", logger="assistant"):
        get_text(tmp_path, failing)
    assert "OSError" in caplog.text
    assert "Secret" not in caplog.text


def test_module_exposes_read_only_scope():
    assert cal.SCOPES == ["https://www.googleapis.com/auth/calendar.readonly"]
    assert isinstance(Path("x"), Path)
