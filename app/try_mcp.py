"""Manual check: act as an MCP client. Start our server, discover its tools, call one.

Run: python -m app.try_mcp
"""

import asyncio
import sys

from mcp import Client, StdioServerParameters


async def main() -> None:
    # The client launches our server as a subprocess and talks to it over stdin/stdout.
    server = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server"])
    async with Client(server) as client:
        print("1. Discovery: the client asks the server what it offers")
        for tool in (await client.list_tools()).tools:
            print(f"   tool: {tool.name}")
            print(f"   description: {tool.description}")
            print(f"   inputs: {tool.input_schema['properties'] or 'none'}")
        print("\n2. Call: the client asks the server to run the tool")
        result = await client.call_tool("get_weather", {})
        print(f"   error: {result.is_error}")
        for line in result.content[0].text.splitlines():
            print(f"   {line}")


if __name__ == "__main__":
    asyncio.run(main())
