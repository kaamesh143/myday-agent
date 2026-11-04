"""Load settings from environment variables (.env in Docker)."""

import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def parse_user_ids(raw: str) -> frozenset[int]:
    """Turn "123, 456" into {123, 456}. Ignores blanks; rejects non-numbers."""
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.lstrip("-").isdigit():
            raise ValueError(f"ALLOWED_USER_IDS contains a non-numeric value: {part!r}")
        ids.add(int(part))
    return frozenset(ids)


def parse_list(raw: str) -> tuple[str, ...]:
    """Turn "a, b,,c" into ("a", "b", "c")."""
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def parse_time_of_day(raw: str, timezone: str) -> datetime.time:
    """Turn "07:00" and "Europe/Stockholm" into a time that follows daylight saving."""
    try:
        hour_text, minute_text = raw.strip().split(":")
        return datetime.time(int(hour_text), int(minute_text), tzinfo=ZoneInfo(timezone))
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError(
            f"MYDAY_TIME must look like 07:00 and TZ must be a real timezone (got {raw!r}, {timezone!r})"
        ) from exc


def parse_days(raw: str) -> int:
    """TRIP_DAYS_AHEAD: a whole number of days from 0 to 365."""
    raw = raw.strip() or "30"
    if not raw.isdigit() or int(raw) > 365:
        raise SystemExit(f"TRIP_DAYS_AHEAD must be a whole number from 0 to 365 (got {raw!r})")
    return int(raw)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    anthropic_api_key: str
    allowed_user_ids: frozenset[int]
    timezone: str
    myday_time: datetime.time  # when the daily brief is sent, in the owner's timezone
    google_token_path: Path
    calendar_ids: tuple[str, ...]  # calendars shown in /myday ("primary" is your main one)
    private_calendar_ids: frozenset[str]  # calendars whose events are shown as "Busy"
    weather_source: str = "direct"  # "direct" or "mcp" (Lab 3: the bot asks our MCP server)
    trip_cache_path: Path = Path("data/trip_cache.json")  # trip items found in Gmail
    trip_gmail_query: str = ""  # empty means the built-in booking search
    trip_days_ahead: int = 30  # how far ahead /myday shows trip items


WEATHER_SOURCES = ("direct", "mcp")


def load_settings() -> Settings:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
    timezone = os.environ.get("TZ", "Europe/Stockholm")
    try:
        myday_time = parse_time_of_day(os.environ.get("MYDAY_TIME", "07:00"), timezone)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    weather_source = os.environ.get("WEATHER_SOURCE", "direct").strip().lower() or "direct"
    if weather_source not in WEATHER_SOURCES:
        raise SystemExit(
            f"WEATHER_SOURCE must be one of {', '.join(WEATHER_SOURCES)} (got {weather_source!r})"
        )
    return Settings(
        bot_token=token,
        anthropic_api_key=api_key,
        allowed_user_ids=parse_user_ids(os.environ.get("ALLOWED_USER_IDS", "")),
        timezone=timezone,
        myday_time=myday_time,
        google_token_path=Path(os.environ.get("GOOGLE_TOKEN_FILE", "data/token.json")),
        calendar_ids=parse_list(os.environ.get("CALENDAR_IDS", "")) or ("primary",),
        private_calendar_ids=frozenset(parse_list(os.environ.get("CALENDAR_PRIVATE_IDS", ""))),
        weather_source=weather_source,
        trip_cache_path=Path(os.environ.get("TRIP_CACHE_FILE", "data/trip_cache.json")),
        trip_gmail_query=os.environ.get("TRIP_GMAIL_QUERY", "").strip(),
        trip_days_ahead=parse_days(os.environ.get("TRIP_DAYS_AHEAD", "30")),
    )
