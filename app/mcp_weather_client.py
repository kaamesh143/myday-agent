"""Lab 3: the bot as an MCP client. Ask our own MCP server (app/mcp_server.py) for the weather.

Before this lab the bot called app/weather.py directly. Now it can do what Claude Desktop does:
start the server as a small subprocess, talk to it over stdin/stdout, and call its get_weather tool.

Two kinds of failure, handled differently by the caller (app/myday.py):
- McpUnavailableError: MCP itself broke (server did not start, timed out, odd reply).
  The weather service may be fine, so the caller falls back to the direct call.
- WeatherError: the server ran the tool and the weather service was down.
  A direct call would hit the same service again, so the caller does not retry.
"""

import asyncio
import logging
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

from app.weather import WeatherError

log = logging.getLogger("assistant")

TOOL_NAME = "get_weather"
# The server's own weather call can take up to about 21 s (two 10 s tries and a 1 s wait),
# plus a second or two to start Python. After this we give up and use the direct call.
TIMEOUT_SECONDS = 30.0
# The folder that holds app/, so "python -m app.mcp_server" works wherever the bot was started.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class McpUnavailableError(Exception):
    """The MCP server could not be reached or gave a reply we did not understand."""


def server_parameters() -> StdioServerParameters:
    """How to start our server: the same Python as the bot, in the project folder.

    We pass no env, so the SDK gives the subprocess only a few safe variables (HOME, PATH, ...).
    The bot's secrets (Telegram token, Anthropic key) never reach the server, which needs none.
    """
    return StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server"], cwd=PROJECT_ROOT)


async def _call_tool(server: object) -> tuple[str, str]:
    """Connect, call the tool once, and turn its text into our two lines."""
    async with Client(server, read_timeout_seconds=TIMEOUT_SECONDS) as client:
        result = await client.call_tool(TOOL_NAME, {})
    text = result.content[0].text if result.content else ""
    if result.is_error:
        # The server's ToolError message is short and safe ("Weather is not available right now.").
        raise WeatherError(text or "Weather is not available right now.")
    lines = text.splitlines()
    if len(lines) != 2:
        raise McpUnavailableError(f"Expected 2 lines from {TOOL_NAME}, got {len(lines)}")
    return lines[0], lines[1]


def get_weather_lines_via_mcp(server: object | None = None) -> tuple[str, str]:
    """Ask the MCP server for today's weather. Blocking: call it from a thread, like the direct call.

    `server` is for tests: they pass the in-memory server object instead of starting a process.
    """
    target = server if server is not None else server_parameters()
    try:
        return asyncio.run(asyncio.wait_for(_call_tool(target), TIMEOUT_SECONDS))
    except (WeatherError, McpUnavailableError):
        raise
    except Exception as exc:  # any MCP problem means "use the fallback"
        # Log only the error type, never message contents.
        raise McpUnavailableError(type(exc).__name__) from exc
