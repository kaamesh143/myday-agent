import asyncio
import sys

from mcp import Client, StdioServerParameters

import app.mcp_server as mcp_server
from app.agent import WEATHER_TOOL
from app.weather import WeatherError

LINES = ("Dry and calm all day.", "Max 11° / Min 8°. No extra gear needed.")


def with_client(action):
    """Connect a client to our server in memory, run the async action, return its result."""

    async def run():
        async with Client(mcp_server.server) as client:
            return await action(client)

    return asyncio.run(run())


def test_server_offers_exactly_one_tool():
    tools = with_client(lambda client: client.list_tools()).tools
    assert [tool.name for tool in tools] == ["get_weather"]


def test_tool_description_is_shared_with_our_own_agent():
    tool = with_client(lambda client: client.list_tools()).tools[0]
    assert tool.description == WEATHER_TOOL.description


def test_tool_takes_no_inputs_and_is_marked_read_only():
    tool = with_client(lambda client: client.list_tools()).tools[0]
    assert tool.input_schema["properties"] == {}
    assert tool.annotations.read_only_hint is True


def test_calling_the_tool_returns_the_two_lines(monkeypatch):
    monkeypatch.setattr(mcp_server, "get_weather_lines", lambda: LINES)
    result = with_client(lambda client: client.call_tool("get_weather", {}))
    assert result.is_error is False
    assert result.content[0].text == "Dry and calm all day.\nMax 11° / Min 8°. No extra gear needed."


def test_expected_failure_reaches_the_client_as_a_short_error(monkeypatch):
    def failing():
        raise WeatherError("Weather is not available right now.")

    monkeypatch.setattr(mcp_server, "get_weather_lines", failing)
    result = with_client(lambda client: client.call_tool("get_weather", {}))
    assert result.is_error is True
    assert "Weather is not available right now." in result.content[0].text


def test_unexpected_failure_does_not_leak_details_to_the_client(monkeypatch):
    def failing():
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(mcp_server, "get_weather_lines", failing)
    result = with_client(lambda client: client.call_tool("get_weather", {}))
    assert result.is_error is True
    assert "secret" not in result.content[0].text


def test_real_stdio_transport_works():
    """Start the server as a separate process, like Claude Desktop would, and list its tools."""

    async def run():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server"])
        async with Client(parameters) as client:
            return await client.list_tools()

    assert [tool.name for tool in asyncio.run(run()).tools] == ["get_weather"]
