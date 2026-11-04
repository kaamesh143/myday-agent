"""The /myday message: today's calendar and weather.

This is a fixed pipeline: our code fetches each part in the same order every time,
so no AI is needed to decide what to fetch.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from app.calendar_source import get_calendar_text
from app.mcp_weather import get_weather_lines_preferring_mcp
from app.weather import WeatherError, get_weather_lines

log = logging.getLogger("assistant")


@dataclass(frozen=True)
class MyDayConfig:
    timezone: str
    google_token_path: Path
    calendar_ids: tuple[str, ...]
    private_calendar_ids: frozenset[str]
    # True: ask our MCP server for the weather (Lab 3), with the direct call as fallback.
    # The bot sets this from WEATHER_VIA_MCP. Off by default so tests never start a subprocess.
    weather_via_mcp: bool = False


def build_myday_message(config: MyDayConfig) -> str:
    """Fetch everything for today and return the text to send. Never raises for data problems."""
    calendar = get_calendar_text(
        config.google_token_path,
        config.timezone,
        config.calendar_ids,
        config.private_calendar_ids,
    )
    try:
        fetch_weather = get_weather_lines_preferring_mcp if config.weather_via_mcp else get_weather_lines
        first_line, second_line = fetch_weather()
        weather = f"{first_line}\n{second_line}"
    except WeatherError:
        log.warning("Weather could not be fetched for /myday")
        weather = "Weather is not available right now."
    return f"Today\n{calendar}\n\nWeather today\n{weather}"
