"""Today's weather as two short lines: what to expect and what to take with you.

Uses Open-Meteo (free, no API key). All the rules are plain code, no AI.
"""

from dataclasses import dataclass

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 10

# Malmö. Later this moves to settings so anyone can use their own location.
DEFAULT_LATITUDE = 55.605
DEFAULT_LONGITUDE = 13.004
DEFAULT_TIMEZONE = "Europe/Stockholm"


class WeatherError(Exception):
    """The forecast could not be fetched or understood."""


@dataclass(frozen=True)
class Rules:
    first_hour: int = 6  # hours from here ...
    last_hour: int = 22  # ... up to (not including) here are checked
    rain_mm: float = 0.2  # an hour with at least this much precipitation counts as wet
    snow_cm: float = 0.1  # an hour with at least this much snowfall counts as snow
    gust_kmh: float = 50.0  # gusts at or above this count as windy
    freezing_c: float = 0.0  # a daily minimum below this means winter clothes


DEFAULT_RULES = Rules()


def fetch_forecast(
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str = DEFAULT_TIMEZONE,
    client: httpx.Client | None = None,
) -> dict:
    """Download today's hourly and daily forecast as raw data."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,precipitation,snowfall,wind_gusts_10m",
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": timezone,
        "forecast_days": 1,
    }
    try:
        if client is None:
            with httpx.Client(timeout=TIMEOUT_SECONDS) as own_client:
                response = own_client.get(FORECAST_URL, params=params)
        else:
            response = client.get(FORECAST_URL, params=params)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise WeatherError("Weather is not available right now.") from exc


def _windows(hours: list[int]) -> list[tuple[int, int]]:
    """Group hours like [14, 15, 16, 20] into ranges [(14, 17), (20, 21)] (end is exclusive)."""
    ranges: list[tuple[int, int]] = []
    for hour in sorted(hours):
        if ranges and ranges[-1][1] == hour:
            ranges[-1] = (ranges[-1][0], hour + 1)
        else:
            ranges.append((hour, hour + 1))
    return ranges


def _format_windows(windows: list[tuple[int, int]]) -> str:
    return ", ".join(f"{start:02d}:00–{end:02d}:00" for start, end in windows)


def _whole(value: float) -> int:
    """Round to a whole degree. Python's int() avoids showing '-0'."""
    return int(round(value))


def summarize(forecast: dict, rules: Rules = DEFAULT_RULES) -> tuple[str, str]:
    """Turn the raw forecast into two short lines."""
    try:
        hourly = forecast["hourly"]
        daily = forecast["daily"]
        times = hourly["time"]
        day_max = daily["temperature_2m_max"][0]
        day_min = daily["temperature_2m_min"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise WeatherError("Weather data was not in the expected format.") from exc
    if day_max is None or day_min is None:
        raise WeatherError("Weather data was not in the expected format.")

    rain_hours, snow_hours, wind_hours = [], [], []
    peak_gust = 0.0
    for index, stamp in enumerate(times):
        hour = int(stamp[11:13])
        if not rules.first_hour <= hour < rules.last_hour:
            continue
        # The service can return null for missing values: treat them as zero.
        precipitation = hourly["precipitation"][index] or 0.0
        snowfall = hourly["snowfall"][index] or 0.0
        gust = hourly["wind_gusts_10m"][index] or 0.0
        if snowfall >= rules.snow_cm:
            snow_hours.append(hour)
        elif precipitation >= rules.rain_mm:
            rain_hours.append(hour)
        if gust >= rules.gust_kmh:
            wind_hours.append(hour)
            peak_gust = max(peak_gust, gust)

    rain, snow, wind = _windows(rain_hours), _windows(snow_hours), _windows(wind_hours)

    wet_parts = []
    if rain:
        wet_parts.append(f"rain {_format_windows(rain)}")
    if snow:
        wet_parts.append(f"snow {_format_windows(snow)}")
    wet_text = ", ".join(wet_parts)
    wet_text = wet_text[:1].upper() + wet_text[1:]
    wind_text = f"Windy {_format_windows(wind)} (gusts up to {_whole(peak_gust)} km/h)" if wind else ""

    if wet_text and wind_text:
        first_line = f"{wet_text}. {wind_text}."
    elif wet_text:
        first_line = f"{wet_text}."
    elif wind_text:
        first_line = f"No rain or snow. {wind_text}."
    else:
        first_line = "Dry and calm all day."

    freezing = day_min < rules.freezing_c
    gear = []
    if rain:
        gear.append("an umbrella")
    if freezing:
        gear.append("a winter jacket")
    if freezing or snow:
        gear.append("boots")
    if len(gear) > 1:
        gear_text = ", ".join(gear[:-1]) + " and " + gear[-1]
    else:
        gear_text = "".join(gear)
    advice = f"Take {gear_text}." if gear else "No extra gear needed."
    second_line = f"Max {_whole(day_max)}° / Min {_whole(day_min)}°. {advice}"
    return first_line, second_line


def get_weather_lines(
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
) -> tuple[str, str]:
    """Fetch today's forecast and return the two summary lines."""
    return summarize(fetch_forecast(latitude, longitude))
