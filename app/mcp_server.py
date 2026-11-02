"""Our weather tool as an MCP server.

MCP (Model Context Protocol) is a standard way to offer tools. Written once here, the tool
can be used by any MCP client: Claude Desktop, Claude Code, or our own code.

The server talks to its client over stdin/stdout (the "stdio" transport), so it opens no
network port. Never print to stdout in this file: it would corrupt the protocol.
Run it with: python -m app.mcp_server
"""

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app.agent import WEATHER_TOOL
from app.weather import WeatherError, get_weather_lines

server = MCPServer(
    "myday-weather",
    instructions="Today's weather summary for the owner's home city. Read-only.",
)


@server.tool(
    name=WEATHER_TOOL.name,
    # One description for both our own agent and this server, so they cannot drift apart.
    description=WEATHER_TOOL.description,
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True),
)
def get_weather() -> str:
    """Return the two weather lines.

    A WeatherError is a failure we expect, so its short message goes to the client as a ToolError.
    Anything unexpected is hidden by the SDK, which sends the client only a generic error.
    """
    try:
        first_line, second_line = get_weather_lines()
    except WeatherError as exc:
        raise ToolError(str(exc)) from exc
    return f"{first_line}\n{second_line}"


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
