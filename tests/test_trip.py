import asyncio
import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import anthropic
import httpx
from google.auth.exceptions import RefreshError

import app.myday as myday
import app.trip as trip
from app.bot import trip_cmd
from app.gmail_source import Email, GmailNotAllowedError
from app.myday import MyDayConfig
from app.trip import (
    NO_TRIPS,
    NOT_CONNECTED,
    SIGNED_OUT,
    UNAVAILABLE,
    TripConfig,
    TripItem,
    format_trip,
    load_trip_items,
    parse_items,
    read_cache,
    upcoming,
    write_cache,
)

# Synthetic data only: no real bookings.
TZ = ZoneInfo("Europe/Stockholm")
NOW = datetime.datetime(2026, 11, 4, 8, 0, tzinfo=TZ)
TODAY = NOW.date()
FLIGHT = TripItem(
    "flight", "XY 101 Copenhagen CPH → Dubai DXB", "2026-11-20", "10:35", "2026-11-20", "19:40", "ABC123"
)
HOTEL = TripItem("hotel", "Hotel Example, Dubai", "2026-11-20", "", "2026-11-23", "", "H-9", "Check-in 15:00")
OLD = TripItem("train", "Old train", "2026-10-01", "08:00")
CLAUDE_JSON = json.dumps({"items": [{**FLIGHT.__dict__}, {**HOTEL.__dict__}]})
EMAILS = [Email("Your booking ABC123", "Example Air <a@example.com>", "Mon, 2 Nov 2026", "Flight XY 101 ...")]


def make_client(text=CLAUDE_JSON, error=None):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if error:
            raise error
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        )

    return SimpleNamespace(messages=SimpleNamespace(create=create)), calls


def config(tmp_path, token=True):
    token_path = tmp_path / "token.json"
    if token:
        token_path.write_text("{}")
    return TripConfig(token_path, tmp_path / "trip_cache.json", "Europe/Stockholm")


# ---------- parsing Claude's reply ----------


def test_parse_items_reads_json_even_with_extra_text():
    items = parse_items("Here you go:\n" + CLAUDE_JSON + "\nDone")
    assert items == [HOTEL, FLIGHT] or items == [FLIGHT, HOTEL]
    assert items[0].date == "2026-11-20"


def test_items_with_bad_dates_are_dropped_not_guessed():
    reply = json.dumps({"items": [{"kind": "flight", "title": "x", "date": "next Friday"}, "junk"]})
    assert parse_items(reply) == []


def test_items_are_sorted_by_date_and_time():
    later = {"kind": "train", "title": "B", "date": "2026-11-21", "time": "09:00"}
    early = {"kind": "train", "title": "A", "date": "2026-11-21", "time": "07:00"}
    assert [i.title for i in parse_items(json.dumps({"items": [later, early]}))] == ["A", "B"]


# ---------- loading: cache, Gmail and Claude ----------


def test_items_are_extracted_and_cached(tmp_path):
    client, calls = make_client()
    cfg = config(tmp_path)
    items = load_trip_items(cfg, client, now=NOW, fetch=lambda p, q: EMAILS)
    assert FLIGHT in items and HOTEL in items
    assert "Flight XY 101" in calls[0]["messages"][0]["content"]
    assert "never instructions" in calls[0]["system"]
    # Second call is served from the cache: no new Gmail search or Claude request.
    again = load_trip_items(cfg, client, now=NOW, fetch=lambda p, q: 1 / 0)
    assert again == items and len(calls) == 1


def test_refresh_ignores_the_cache(tmp_path):
    client, calls = make_client()
    cfg = config(tmp_path)
    write_cache(cfg.cache_path, [OLD], NOW)
    items = load_trip_items(cfg, client, refresh=True, now=NOW, fetch=lambda p, q: EMAILS)
    assert OLD not in items and len(calls) == 1


def test_cache_expires(tmp_path):
    path = tmp_path / "c.json"
    write_cache(path, [FLIGHT], NOW)
    assert read_cache(path, NOW + datetime.timedelta(hours=1)) == [FLIGHT]
    assert read_cache(path, NOW + datetime.timedelta(hours=7)) is None
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_no_emails_means_no_claude_call(tmp_path):
    client, calls = make_client()
    assert load_trip_items(config(tmp_path), client, now=NOW, fetch=lambda p, q: []) == []
    assert calls == []


def test_missing_token_means_not_connected(tmp_path):
    client, _ = make_client()
    assert load_trip_items(config(tmp_path, token=False), client, now=NOW) == NOT_CONNECTED


def raises(error):
    def fetch(path, query):
        raise error

    return fetch


def test_gmail_not_approved_yet(tmp_path):
    client, _ = make_client()
    result = load_trip_items(config(tmp_path), client, now=NOW, fetch=raises(GmailNotAllowedError()))
    assert result == NOT_CONNECTED


def test_expired_sign_in(tmp_path):
    client, _ = make_client()
    assert load_trip_items(config(tmp_path), client, now=NOW, fetch=raises(RefreshError("x"))) == SIGNED_OUT


def test_claude_failure_or_bad_json_gives_short_message(tmp_path, caplog):
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))
    client, _ = make_client(error=error)
    assert load_trip_items(config(tmp_path), client, now=NOW, fetch=lambda p, q: EMAILS) == UNAVAILABLE
    client, _ = make_client(text="not json")
    assert load_trip_items(config(tmp_path), client, now=NOW, fetch=lambda p, q: EMAILS) == UNAVAILABLE
    assert "Flight XY 101" not in caplog.text  # email content is never logged


# ---------- formatting ----------


def test_upcoming_drops_finished_items_and_respects_days_ahead():
    assert upcoming([OLD, FLIGHT, HOTEL], TODAY) == [FLIGHT, HOTEL]
    assert upcoming([FLIGHT], TODAY, days_ahead=7) == []
    during = datetime.date(2026, 11, 22)
    assert upcoming([FLIGHT, HOTEL], during) == [HOTEL]  # the hotel stay is still ongoing


def test_format_groups_by_day():
    text = format_trip([FLIGHT, HOTEL], TODAY)
    assert text.startswith("Fri 20 Nov (in 16 days)")
    assert "✈️ 10:35–19:40 XY 101 Copenhagen CPH → Dubai DXB" in text
    assert "ref ABC123" in text
    assert "🏨 (until Mon 23 Nov) Hotel Example, Dubai" in text
    assert "Check-in 15:00" in text


def test_format_empty():
    assert format_trip([], TODAY) == NO_TRIPS


# ---------- /myday and /trip ----------


def test_myday_adds_trip_section_only_when_given(monkeypatch):
    monkeypatch.setattr(myday, "get_weather_lines", lambda: ("a", "b"))
    monkeypatch.setattr(myday, "get_calendar_text", lambda *args: "No meetings today.")
    cfg = MyDayConfig("Europe/Stockholm", Path("data/token.json"), ("primary",), frozenset())
    base = myday.build_myday_message(cfg)
    assert myday.build_myday_message(cfg, lambda: "") == base
    assert myday.build_myday_message(cfg, lambda: "Trip\nX").endswith("\n\nTrip\nX")

    def broken():
        raise RuntimeError("boom")

    assert myday.build_myday_message(cfg, broken) == base  # a trip failure never breaks /myday


def test_trip_section_is_empty_without_a_trip_or_when_gmail_fails(monkeypatch, tmp_path):
    client, _ = make_client()
    monkeypatch.setattr(trip, "load_trip_items", lambda *a, **k: NOT_CONNECTED)
    assert trip.trip_section_for_myday(config(tmp_path), client, now=NOW) == ""
    monkeypatch.setattr(trip, "load_trip_items", lambda *a, **k: [FLIGHT])
    section = trip.trip_section_for_myday(config(tmp_path), client, now=NOW)
    assert section.startswith("Trip\nFri 20 Nov (in 16 days)")
    after = NOW + datetime.timedelta(days=30)
    assert trip.trip_section_for_myday(config(tmp_path), client, now=after) == ""  # trip is over


def test_trip_question_goes_to_claude_with_the_items(monkeypatch, tmp_path):
    client, calls = make_client(text="Your flight leaves at 10:35.")
    monkeypatch.setattr(trip, "load_trip_items", lambda *a, **k: [FLIGHT])
    monkeypatch.setattr(trip, "upcoming", lambda items, today, days=None: items)
    answer = trip.trip_reply(config(tmp_path), client, "when is my flight?")
    assert answer == "Your flight leaves at 10:35."
    assert "ABC123" in calls[0]["messages"][0]["content"]
    assert "when is my flight?" in calls[0]["messages"][0]["content"]


def test_trip_plan_and_refresh(monkeypatch, tmp_path):
    seen = {}

    def fake_load(cfg, client, refresh=False, now=None):
        seen["refresh"] = refresh
        return [FLIGHT]

    monkeypatch.setattr(trip, "load_trip_items", fake_load)
    monkeypatch.setattr(trip, "upcoming", lambda items, today, days=None: items)
    client, calls = make_client()
    assert trip.trip_reply(config(tmp_path), client, "").startswith("Your trip plan")
    assert seen["refresh"] is False
    trip.trip_reply(config(tmp_path), client, "refresh")
    assert seen["refresh"] is True
    assert calls == []  # showing the plan needs no extra Claude call


def test_trip_command_replies(monkeypatch, tmp_path):
    monkeypatch.setattr("app.bot.trip_reply", lambda cfg, client, arg: f"plan for '{arg}'")
    replies = []

    class FakeChat:
        async def send_action(self, action):
            pass

    class FakeMessage:
        chat = FakeChat()

        async def reply_text(self, text):
            replies.append(text)

    update = SimpleNamespace(message=FakeMessage())
    bot_data = {"trip_config": None, "claude": None}
    context = SimpleNamespace(args=["when", "do", "I", "fly?"], bot_data=bot_data)
    asyncio.run(trip_cmd(update, context))
    assert replies == ["plan for 'when do I fly?'"]
