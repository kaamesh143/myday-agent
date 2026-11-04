import asyncio
import logging
import os
import sys
from pathlib import Path

import pytest
from mcp import StdioServerParameters

import app.agent as agent
import app.mcp_server as mcp_server
import app.mcp_weather as mcp_weather
import app.myday as myday
from app.agent import MCP_WEATHER_TOOL, WEATHER_TOOL
from app.config import load_settings, parse_bool
from app.mcp_weather import MCPUnavailableError, get_weather_lines_preferring_mcp, get_weather_lines_via_mcp
from app.myday import MyDayConfig
from app.weather import WeatherError

LINES = ("Dry and calm all day.", "Max 11° / Min 8°. No extra gear needed.")
DIRECT = ("Direct line one.", "Direct line two.")
# Passing the server object itself connects the client in memory: no subprocess, fast tests.
IN_MEMORY = mcp_server.server


@pytest.fixture
def server_weather(monkeypatch):
    """Control what the server's tool returns, and fail loudly if the direct path is used."""

    def set_lines(lines=LINES):
        monkeypatch.setattr(mcp_server, "get_weather_lines", lambda: lines)

    def direct_must_not_run():
        raise AssertionError("the direct path should not run")

    monkeypatch.setattr(mcp_weather, "get_weather_lines", direct_must_not_run)
    return set_lines


def test_client_discovers_and_calls_the_tool(server_weather):
    server_weather()
    assert get_weather_lines_via_mcp(IN_MEMORY) == LINES


def test_weather_error_from_the_server_becomes_a_weather_error(monkeypatch, server_weather):
    def failing():
        raise WeatherError("Weather is not available right now.")

    monkeypatch.setattr(mcp_server, "get_weather_lines", failing)
    with pytest.raises(WeatherError, match="not available"):
        get_weather_lines_via_mcp(IN_MEMORY)


def test_weather_error_is_not_retried_through_the_direct_path(monkeypatch, server_weather):
    """The direct call would hit the same broken weather service, so we do not try it."""

    def failing():
        raise WeatherError("Weather is not available right now.")

    monkeypatch.setattr(mcp_server, "get_weather_lines", failing)
    with pytest.raises(WeatherError):
        get_weather_lines_preferring_mcp(IN_MEMORY)


def test_missing_tool_means_mcp_is_unavailable(monkeypatch):
    async def ask_server(server):
        return ["some_other_tool"], False, ""

    monkeypatch.setattr(mcp_weather, "_ask_server", ask_server)
    with pytest.raises(MCPUnavailableError, match="does not offer get_weather"):
        get_weather_lines_via_mcp(IN_MEMORY)


def test_unexpected_reply_shape_means_mcp_is_unavailable(monkeypatch):
    async def ask_server(server):
        return ["get_weather"], False, "only one line"

    monkeypatch.setattr(mcp_weather, "_ask_server", ask_server)
    with pytest.raises(MCPUnavailableError, match="Expected 2 lines"):
        get_weather_lines_via_mcp(IN_MEMORY)


def test_timeout_means_mcp_is_unavailable(monkeypatch):
    async def slow(server):
        await asyncio.sleep(5)

    monkeypatch.setattr(mcp_weather, "_ask_server", slow)
    with pytest.raises(MCPUnavailableError, match="No answer"):
        get_weather_lines_via_mcp(IN_MEMORY, timeout=0.05)


def test_falls_back_to_the_direct_call_when_the_server_cannot_start(monkeypatch, caplog):
    monkeypatch.setattr(mcp_weather, "get_weather_lines", lambda: DIRECT)
    broken = StdioServerParameters(command=sys.executable, args=["-m", "app.no_such_module"])
    with caplog.at_level(logging.WARNING, logger="assistant"):
        assert get_weather_lines_preferring_mcp(broken, timeout=10) == DIRECT
    assert "using the direct call instead" in caplog.text


def test_real_subprocess_round_trip_reports_a_clean_weather_error(monkeypatch):
    """Start app/mcp_server.py as a real process, like the bot does in Docker.

    The subprocess cannot see our monkeypatching, so we point its proxy at a closed port.
    Its weather request then fails fast, and the error must come back over MCP as a
    WeatherError, not as a fallback to the direct path.
    """
    monkeypatch.setattr(mcp_weather, "get_weather_lines", lambda: pytest.fail("fell back to direct"))
    offline = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        env={"PATH": os.environ.get("PATH", ""), "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": ""},
    )
    with pytest.raises(WeatherError, match="not available"):
        get_weather_lines_preferring_mcp(offline, timeout=25)


def test_myday_uses_mcp_when_switched_on(monkeypatch):
    monkeypatch.setattr(myday, "get_weather_lines_preferring_mcp", lambda: LINES)
    monkeypatch.setattr(myday, "get_weather_lines", lambda: pytest.fail("direct path used"))
    monkeypatch.setattr(myday, "get_calendar_text", lambda *args: "No meetings today.")
    config = MyDayConfig("Europe/Stockholm", Path("data/token.json"), ("primary",), frozenset(), True)
    assert myday.build_myday_message(config).endswith("\n".join(LINES))


def test_myday_survives_weather_error_over_mcp(monkeypatch):
    def failing():
        raise WeatherError("down")

    monkeypatch.setattr(myday, "get_weather_lines_preferring_mcp", failing)
    monkeypatch.setattr(myday, "get_calendar_text", lambda *args: "No meetings today.")
    config = MyDayConfig("Europe/Stockholm", Path("data/token.json"), ("primary",), frozenset(), True)
    assert myday.build_myday_message(config).endswith("Weather is not available right now.")


def test_agent_mcp_tool_looks_identical_to_claude():
    assert MCP_WEATHER_TOOL.definition() == WEATHER_TOOL.definition()


def test_agent_mcp_tool_runs_through_mcp(monkeypatch):
    monkeypatch.setattr(agent, "get_weather_lines_preferring_mcp", lambda: LINES)
    assert MCP_WEATHER_TOOL.run({}) == "\n".join(LINES)


@pytest.mark.parametrize(("raw", "expected"), [("true", True), ("YES", True), ("0", False), (" off ", False)])
def test_parse_bool(raw, expected):
    assert parse_bool(raw, "X") is expected


def test_parse_bool_rejects_other_values():
    with pytest.raises(ValueError, match="WEATHER_VIA_MCP"):
        parse_bool("maybe", "WEATHER_VIA_MCP")


def test_settings_turn_mcp_on_by_default_and_allow_off(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    monkeypatch.delenv("WEATHER_VIA_MCP", raising=False)
    assert load_settings().weather_via_mcp is True
    monkeypatch.setenv("WEATHER_VIA_MCP", "false")
    assert load_settings().weather_via_mcp is False
    monkeypatch.setenv("WEATHER_VIA_MCP", "banana")
    with pytest.raises(SystemExit):
        load_settings()
