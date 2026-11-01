"""The /myday message. Today it holds the weather; calendar and shares come later.

This is a fixed pipeline: our code fetches each part in the same order every time,
so no AI is needed to decide what to fetch.
"""

import logging

from app.weather import WeatherError, get_weather_lines

log = logging.getLogger("assistant")


def build_myday_message() -> str:
    """Fetch everything for today and return the text to send. Never raises for weather problems."""
    try:
        first_line, second_line = get_weather_lines()
        weather = f"{first_line}\n{second_line}"
    except WeatherError:
        log.warning("Weather could not be fetched for /myday")
        weather = "Weather is not available right now."
    return f"Weather today\n{weather}"
