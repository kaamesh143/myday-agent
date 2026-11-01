import asyncio
import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import anthropic
import pytest
from telegram.error import TelegramError

import app.myday as myday
from app.bot import build_application, myday_cmd, send_daily_myday
from app.config import load_settings, parse_time_of_day
from app.weather import WeatherError

STOCKHOLM = ZoneInfo("Europe/Stockholm")
SEVEN = datetime.time(7, 0, tzinfo=STOCKHOLM)


def fake_weather(monkeypatch, lines=("Dry and calm all day.", "Max 11° / Min 8°. No extra gear needed.")):
    monkeypatch.setattr(myday, "get_weather_lines", lambda: lines)


def test_message_contains_both_weather_lines(monkeypatch):
    fake_weather(monkeypatch)
    assert myday.build_myday_message() == (
        "Weather today\nDry and calm all day.\nMax 11° / Min 8°. No extra gear needed."
    )


def test_message_survives_a_weather_failure(monkeypatch):
    def broken():
        raise WeatherError("down")

    monkeypatch.setattr(myday, "get_weather_lines", broken)
    assert myday.build_myday_message() == "Weather today\nWeather is not available right now."


def test_myday_command_replies_with_the_message(monkeypatch):
    fake_weather(monkeypatch)
    replies = []

    async def reply_text(text):
        replies.append(text)

    update = SimpleNamespace(message=SimpleNamespace(reply_text=reply_text))
    asyncio.run(myday_cmd(update, SimpleNamespace()))
    assert replies == ["Weather today\nDry and calm all day.\nMax 11° / Min 8°. No extra gear needed."]


def test_daily_job_sends_to_every_allowed_user_only(monkeypatch):
    fake_weather(monkeypatch)
    sent = []

    async def send_message(chat_id, text):
        sent.append(chat_id)

    context = SimpleNamespace(
        bot=SimpleNamespace(send_message=send_message),
        bot_data={"allowed_user_ids": frozenset({1, 2})},
    )
    asyncio.run(send_daily_myday(context))
    assert sorted(sent) == [1, 2]


def test_daily_job_keeps_going_when_one_send_fails(monkeypatch):
    fake_weather(monkeypatch)
    sent = []

    async def send_message(chat_id, text):
        if chat_id == 1:
            raise TelegramError("blocked")
        sent.append(chat_id)

    context = SimpleNamespace(
        bot=SimpleNamespace(send_message=send_message),
        bot_data={"allowed_user_ids": frozenset({1, 2})},
    )
    asyncio.run(send_daily_myday(context))
    assert sent == [2]


def make_app(allowed):
    return build_application("123:FAKE", frozenset(allowed), anthropic.Anthropic(api_key="x"), SEVEN)


def test_daily_job_is_scheduled_at_the_chosen_time():
    jobs = make_app({42}).job_queue.get_jobs_by_name("daily_myday")
    assert len(jobs) == 1


def test_no_daily_job_when_nobody_is_allowed():
    assert make_app(set()).job_queue.get_jobs_by_name("daily_myday") == ()


def test_time_follows_daylight_saving():
    time = parse_time_of_day("07:00", "Europe/Stockholm")
    winter = datetime.datetime.combine(datetime.date(2026, 12, 1), time)
    summer = datetime.datetime.combine(datetime.date(2026, 7, 1), time)
    assert winter.utcoffset() == datetime.timedelta(hours=1)
    assert summer.utcoffset() == datetime.timedelta(hours=2)


@pytest.mark.parametrize("raw", ["7", "25:00", "07:61", "seven", ""])
def test_bad_time_is_rejected(raw):
    with pytest.raises(ValueError):
        parse_time_of_day(raw, "Europe/Stockholm")


def test_bad_timezone_is_rejected():
    with pytest.raises(ValueError):
        parse_time_of_day("07:00", "Mars/Olympus")


def test_settings_reads_myday_time(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    monkeypatch.setenv("MYDAY_TIME", "06:30")
    monkeypatch.setenv("TZ", "Europe/Stockholm")
    settings = load_settings()
    assert (settings.myday_time.hour, settings.myday_time.minute) == (6, 30)


def test_settings_exits_on_bad_myday_time(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    monkeypatch.setenv("MYDAY_TIME", "banana")
    with pytest.raises(SystemExit):
        load_settings()
