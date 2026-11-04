"""Get the weather through our own MCP server, with the direct call as a fallback (Lab 3).

In Lab 2 we wrote the server (app/mcp_server.py). Here the bot becomes an MCP *client*:
1. it starts the server as a subprocess (stdio transport, no network port),
2. asks which tools it offers (discovery), and
3. calls get_weather and reads the text back.

Two kinds of failure are handled differently:
- MCP itself is broken (server will not start, tool missing, timeout, odd reply):
  we fall back to calling get_weather_lines() directly, so /myday keeps working.
- The server answered with an error (the weather service is down): we raise WeatherError
  and do NOT fall back, because the direct call would hit the same broken weather service.
"""

import asyncio
import logging
import sys
from typing import Any

from mcp import Client, StdioServerParameters

from app.weather import WeatherError, get_weather_lines

log = logging.getLogger("assistant")

TOOL_NAME = "get_weather"
# weather.py can take up to ~21 s on its own (two 10 s tries and a 1 s wait), plus server start-up.
TIMEOUT_SECONDS = 30.0
# The same command Claude Desktop would run. sys.executable is the Python running the bot,
# so inside Docker this is the container's Python with all our packages installed.
SERVER = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server"])


class MCPUnavailableError(Exception):
    """MCP itself failed: the server did not start, the tool was missing, or no answer in time."""


async def _ask_server(server: Any) -> tuple[list[str], bool, str]:
    """Connect, discover, call. Returns (tool names, is_error, text).

    Decisions happen in the caller, outside the `async with`. Exceptions raised inside it can
    come out wrapped in an ExceptionGroup, which would make them harder to catch.
    """
    async with Client(server) as client:
        names = [tool.name for tool in (await client.list_tools()).tools]
        if TOOL_NAME not in names:
            return names, False, ""
        result = await client.call_tool(TOOL_NAME, {})
    text = "".join(block.text for block in result.content if block.type == "text")
    return names, result.is_error, text


def get_weather_lines_via_mcp(server: Any = SERVER, timeout: float = TIMEOUT_SECONDS) -> tuple[str, str]:
    """Return the two weather lines by calling the get_weather tool over MCP.

    Raises WeatherError if the server reports a weather problem, and MCPUnavailableError if
    MCP itself fails. Must not be called from inside a running event loop (asyncio.run would
    refuse), so async code like bot.py runs it with asyncio.to_thread.
    """
    try:
        names, is_error, text = asyncio.run(asyncio.wait_for(_ask_server(server), timeout))
    except TimeoutError as exc:
        raise MCPUnavailableError(f"No answer from the MCP server within {timeout:.0f} s") from exc
    except Exception as exc:  # server failed to start, crashed, or broke the protocol
        raise MCPUnavailableError(f"MCP call failed: {type(exc).__name__}") from exc

    if TOOL_NAME not in names:
        raise MCPUnavailableError(f"The MCP server does not offer {TOOL_NAME} (it offers {names})")
    if is_error:
        # The server already turned this into a short, safe message (see mcp_server.py).
        raise WeatherError(text or "Weather is not available right now.")
    lines = text.splitlines()
    if len(lines) != 2:
        raise MCPUnavailableError(f"Expected 2 lines from {TOOL_NAME}, got {len(lines)}")
    return lines[0], lines[1]


def get_weather_lines_preferring_mcp(
    server: Any = SERVER, timeout: float = TIMEOUT_SECONDS
) -> tuple[str, str]:
    """Try MCP first. If MCP itself is broken, call the weather code directly instead.

    A WeatherError (weather service down) is passed on, with no second attempt.
    """
    try:
        return get_weather_lines_via_mcp(server, timeout)
    except MCPUnavailableError as exc:
        # The reason holds no secrets (tool names, counts, exception type), so it is safe to log.
        log.warning("Weather over MCP failed, using the direct call instead: %s", exc)
        return get_weather_lines()
