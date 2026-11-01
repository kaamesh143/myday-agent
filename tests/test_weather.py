import copy
import json
from pathlib import Path

import httpx
import pytest

from app.weather import WeatherError, fetch_forecast, summarize

FIXTURE = Path(__file__).parent / "fixtures" / "malmo_dry_day.json"


def dry_day() -> dict:
    """A real Malmö forecast: dry, gusts at most 25 km/h, 7.7 to 10.9 degrees."""
    return json.loads(FIXTURE.read_text())


def with_hours(*, rain=(), snow=(), gust=(), day_min=None, day_max=None, gust_kmh=60.0) -> dict:
    """Copy of the dry day with chosen hours made wet, snowy or windy."""
    data = copy.deepcopy(dry_day())
    for hour in rain:
        data["hourly"]["precipitation"][hour] = 1.0
    for hour in snow:
        data["hourly"]["precipitation"][hour] = 0.5
        data["hourly"]["snowfall"][hour] = 0.8
    for hour in gust:
        data["hourly"]["wind_gusts_10m"][hour] = gust_kmh
    if day_min is not None:
        data["daily"]["temperature_2m_min"] = [day_min]
    if day_max is not None:
        data["daily"]["temperature_2m_max"] = [day_max]
    return data


def test_real_dry_day():
    assert summarize(dry_day()) == (
        "Dry and calm all day.",
        "Max 11° / Min 8°. No extra gear needed.",
    )


def test_rain_window_and_umbrella():
    first, second = summarize(with_hours(rain=[14, 15, 16]))
    assert first == "Rain 14:00–17:00."
    assert second.endswith("Take an umbrella.")


def test_rain_and_snow_windows():
    first, _ = summarize(with_hours(rain=[8, 9], snow=[20, 21]))
    assert first == "Rain 08:00–10:00, snow 20:00–22:00."


def test_two_separate_rain_windows():
    first, _ = summarize(with_hours(rain=[7, 8, 15]))
    assert first == "Rain 07:00–09:00, 15:00–16:00."


def test_wind_window_with_peak_gust():
    first, second = summarize(with_hours(gust=[12, 13, 14], gust_kmh=63.0))
    assert first == "No rain or snow. Windy 12:00–15:00 (gusts up to 63 km/h)."
    assert "No extra gear" in second


def test_gust_below_threshold_is_not_windy():
    first, _ = summarize(with_hours(gust=[12], gust_kmh=49.9))
    assert first == "Dry and calm all day."


def test_rain_and_wind_together():
    first, _ = summarize(with_hours(rain=[10], gust=[10]))
    assert first == "Rain 10:00–11:00. Windy 10:00–11:00 (gusts up to 60 km/h)."


def test_freezing_day_needs_jacket_and_boots():
    _, second = summarize(with_hours(day_min=-2.4, day_max=1.2))
    assert second == "Max 1° / Min -2°. Take a winter jacket and boots."


def test_snow_adds_boots_even_above_freezing():
    _, second = summarize(with_hours(snow=[9], day_min=1.0))
    assert second.endswith("Take boots.")


def test_everything_at_once():
    _, second = summarize(with_hours(rain=[9], snow=[18], day_min=-1.0, day_max=2.0))
    assert second.endswith("Take an umbrella, a winter jacket and boots.")


def test_night_hours_are_ignored():
    first, _ = summarize(with_hours(rain=[2, 3], snow=[23], gust=[4]))
    assert first == "Dry and calm all day."


def test_boundary_hours_follow_the_06_to_22_window():
    first, _ = summarize(with_hours(rain=[5, 6, 21, 22]))
    assert first == "Rain 06:00–07:00, 21:00–22:00."


def test_slightly_negative_minimum_is_not_shown_as_minus_zero():
    _, second = summarize(with_hours(day_min=-0.4))
    assert "Min 0°" in second
    assert "-0" not in second


def test_missing_values_are_treated_as_zero():
    data = dry_day()
    data["hourly"]["precipitation"][10] = None
    data["hourly"]["wind_gusts_10m"][11] = None
    assert summarize(data)[0] == "Dry and calm all day."


def test_unexpected_format_raises():
    with pytest.raises(WeatherError):
        summarize({"hourly": {}})


def test_missing_daily_temperature_raises():
    data = dry_day()
    data["daily"]["temperature_2m_min"] = [None]
    with pytest.raises(WeatherError):
        summarize(data)


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_sends_expected_query_and_returns_json():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=dry_day())

    data = fetch_forecast(client=make_client(handler))
    assert data["daily"]["temperature_2m_max"] == [10.9]
    assert seen["params"]["timezone"] == "Europe/Stockholm"
    assert seen["params"]["forecast_days"] == "1"
    assert "wind_gusts_10m" in seen["params"]["hourly"]


def test_fetch_turns_server_error_into_weather_error():
    client = make_client(lambda request: httpx.Response(500))
    with pytest.raises(WeatherError):
        fetch_forecast(client=client)


def test_fetch_turns_network_failure_into_weather_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network", request=request)

    with pytest.raises(WeatherError):
        fetch_forecast(client=make_client(handler))


def test_fetch_turns_bad_json_into_weather_error():
    client = make_client(lambda request: httpx.Response(200, content=b"not json"))
    with pytest.raises(WeatherError):
        fetch_forecast(client=client)
