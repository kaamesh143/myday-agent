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
    weather_via_mcp: bool  # get the weather through our MCP server (Lab 3), direct call as fallback


def parse_bool(raw: str, name: str) -> bool:
    """Turn "true"/"false" (also yes/no, on/off, 1/0) into a bool. Anything else is an error."""
    value = raw.strip().lower()
    if value in {"true", "yes", "on", "1"}:
        return True
    if value in {"false", "no", "off", "0"}:
        return False
    raise ValueError(f"{name} must be true or false (got {raw!r})")


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
    try:
        weather_via_mcp = parse_bool(os.environ.get("WEATHER_VIA_MCP", "true"), "WEATHER_VIA_MCP")
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return Settings(
        bot_token=token,
        anthropic_api_key=api_key,
        allowed_user_ids=parse_user_ids(os.environ.get("ALLOWED_USER_IDS", "")),
        timezone=timezone,
        myday_time=myday_time,
        google_token_path=Path(os.environ.get("GOOGLE_TOKEN_FILE", "data/token.json")),
        calendar_ids=parse_list(os.environ.get("CALENDAR_IDS", "")) or ("primary",),
        private_calendar_ids=frozenset(parse_list(os.environ.get("CALENDAR_PRIVATE_IDS", ""))),
        weather_via_mcp=weather_via_mcp,
    )
