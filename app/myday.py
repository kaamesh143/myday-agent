"""The /myday message: today's calendar, weather and (when a trip is coming up) the trip plan.

This is a fixed pipeline: our code fetches each part in the same order every time,
so no AI is needed to decide what to fetch.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.calendar_source import get_calendar_text
from app.mcp_weather_client import McpUnavailableError, get_weather_lines_via_mcp
from app.weather import WeatherError, get_weather_lines

log = logging.getLogger("assistant")


@dataclass(frozen=True)
class MyDayConfig:
    timezone: str
    google_token_path: Path
    calendar_ids: tuple[str, ...]
    private_calendar_ids: frozenset[str]
    weather_source: str = "direct"  # "direct" (call Open-Meteo) or "mcp" (ask our MCP server, Lab 3)


def get_weather_for_myday(source: str) -> tuple[str, str]:
    """Get the two weather lines from the chosen source.

    With "mcp", a broken MCP connection falls back to the direct call, so /myday keeps working.
    A WeatherError (the weather service itself is down) is passed on: retrying directly would not help.
    """
    if source == "mcp":
        try:
            return get_weather_lines_via_mcp()
        except McpUnavailableError as exc:
            log.warning("MCP weather failed (%s); using the direct call instead", exc)
    return get_weather_lines()


def build_myday_message(config: MyDayConfig, trip_section: Callable[[], str] | None = None) -> str:
    """Fetch everything for today and return the text to send. Never raises for data problems.

    trip_section returns the trip part, or "" when no trip is coming up (then nothing is added).
    """
    calendar = get_calendar_text(
        config.google_token_path,
        config.timezone,
        config.calendar_ids,
        config.private_calendar_ids,
    )
    try:
        first_line, second_line = get_weather_for_myday(config.weather_source)
        weather = f"{first_line}\n{second_line}"
    except WeatherError:
        log.warning("Weather could not be fetched for /myday")
        weather = "Weather is not available right now."
    message = f"Today\n{calendar}\n\nWeather today\n{weather}"
    trip = ""
    if trip_section is not None:
        try:
            trip = trip_section()
        except Exception as exc:  # the trip part must never break the daily brief
            log.warning("Trip section failed: %s", type(exc).__name__)
    return f"{message}\n\n{trip}" if trip else message
