import sys
from pathlib import Path

import pytest

import app.mcp_server as mcp_server
import app.mcp_weather_client as mcp_client
import app.myday as myday
from app.config import load_settings
from app.mcp_weather_client import McpUnavailableError, get_weather_lines_via_mcp, server_parameters
from app.myday import MyDayConfig
from app.weather import WeatherError

LINES = ("Dry and calm all day.", "Max 11° / Min 8°. No extra gear needed.")
MCP_CONFIG = MyDayConfig("Europe/Stockholm", Path("data/token.json"), ("primary",), frozenset(), "mcp")


# --- The client on its own (talks to the real server object in memory, no subprocess) ---


def test_client_returns_the_two_lines_from_the_server(monkeypatch):
    monkeypatch.setattr(mcp_server, "get_weather_lines", lambda: LINES)
    assert get_weather_lines_via_mcp(mcp_server.server) == LINES


def test_weather_service_down_is_a_weather_error_not_an_mcp_error(monkeypatch):
    def failing():
        raise WeatherError("Weather is not available right now.")

    monkeypatch.setattr(mcp_server, "get_weather_lines", failing)
    with pytest.raises(WeatherError, match="not available"):
        get_weather_lines_via_mcp(mcp_server.server)


def test_unexpected_reply_shape_is_an_mcp_error(monkeypatch):
    # The server joins the pair with a newline, so an extra newline inside gives 3 lines.
    monkeypatch.setattr(mcp_server, "get_weather_lines", lambda: ("a\nb", "c"))
    with pytest.raises(McpUnavailableError):
        get_weather_lines_via_mcp(mcp_server.server)


def test_server_that_cannot_start_is_an_mcp_error():
    from mcp import StdioServerParameters

    broken = StdioServerParameters(command=sys.executable, args=["-m", "app.no_such_module"])
    with pytest.raises(McpUnavailableError):
        get_weather_lines_via_mcp(broken)


def test_slow_server_times_out_as_an_mcp_error(monkeypatch):
    async def never_answers(server):
        import asyncio

        await asyncio.sleep(10)

    monkeypatch.setattr(mcp_client, "_call_tool", never_answers)
    monkeypatch.setattr(mcp_client, "TIMEOUT_SECONDS", 0.05)
    with pytest.raises(McpUnavailableError, match="TimeoutError"):
        get_weather_lines_via_mcp(mcp_server.server)


def test_server_gets_no_secrets_from_the_bot():
    parameters = server_parameters()
    # env=None makes the SDK pass only HOME, PATH, SHELL and TERM, not TELEGRAM_BOT_TOKEN etc.
    assert parameters.env is None
    assert parameters.args == ["-m", "app.mcp_server"]
    assert (Path(parameters.cwd) / "app" / "mcp_server.py").exists()


# --- /myday choosing the source and falling back ---


def test_myday_uses_mcp_when_configured(monkeypatch):
    monkeypatch.setattr(myday, "get_weather_lines_via_mcp", lambda: LINES)
    monkeypatch.setattr(myday, "get_weather_lines", lambda: pytest.fail("direct call should not run"))
    monkeypatch.setattr(myday, "get_calendar_text", lambda *args: "No meetings today.")
    assert myday.build_myday_message(MCP_CONFIG).endswith("\n".join(LINES))


def test_myday_falls_back_to_direct_when_mcp_breaks(monkeypatch):
    def broken():
        raise McpUnavailableError("BrokenPipeError")

    monkeypatch.setattr(myday, "get_weather_lines_via_mcp", broken)
    monkeypatch.setattr(myday, "get_weather_lines", lambda: LINES)
    monkeypatch.setattr(myday, "get_calendar_text", lambda *args: "No meetings today.")
    assert myday.build_myday_message(MCP_CONFIG).endswith("\n".join(LINES))


def test_myday_does_not_retry_directly_when_weather_service_is_down(monkeypatch):
    def down():
        raise WeatherError("Weather is not available right now.")

    monkeypatch.setattr(myday, "get_weather_lines_via_mcp", down)
    monkeypatch.setattr(myday, "get_weather_lines", lambda: pytest.fail("direct call should not run"))
    monkeypatch.setattr(myday, "get_calendar_text", lambda *args: "No meetings today.")
    assert myday.build_myday_message(MCP_CONFIG).endswith("Weather is not available right now.")


def test_default_config_still_uses_the_direct_call(monkeypatch):
    config = MyDayConfig("Europe/Stockholm", Path("data/token.json"), ("primary",), frozenset())
    assert config.weather_source == "direct"
    monkeypatch.setattr(myday, "get_weather_lines_via_mcp", lambda: pytest.fail("MCP should not run"))
    monkeypatch.setattr(myday, "get_weather_lines", lambda: LINES)
    monkeypatch.setattr(myday, "get_calendar_text", lambda *args: "No meetings today.")
    assert myday.build_myday_message(config).endswith("\n".join(LINES))


# --- The setting ---


@pytest.fixture
def required_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:fake")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")


def test_weather_source_defaults_to_direct(monkeypatch, required_env):
    monkeypatch.delenv("WEATHER_SOURCE", raising=False)
    assert load_settings().weather_source == "direct"


def test_weather_source_can_be_mcp(monkeypatch, required_env):
    monkeypatch.setenv("WEATHER_SOURCE", " MCP ")
    assert load_settings().weather_source == "mcp"


def test_unknown_weather_source_stops_the_bot(monkeypatch, required_env):
    monkeypatch.setenv("WEATHER_SOURCE", "magic")
    with pytest.raises(SystemExit):
        load_settings()
