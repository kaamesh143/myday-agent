# The weather tool as an MCP server

`app/mcp_server.py` offers our weather tool over MCP (Model Context Protocol). Written once,
it can be used by any MCP client.

## How it works

```
MCP client (Claude Desktop, Claude Code, our own code)
   │  1. "What tools do you have?"     → server lists name, description, inputs
   │  2. "Run get_weather"             → the SERVER runs it and returns the text
   ▼
MCP server (app/mcp_server.py, a local process, talking over stdin/stdout)
```

- The **server** owns and runs the tool. The client only asks. The model never runs code.
- Transport is **stdio**: the client starts the server as a subprocess. No network port is opened.
- The tool is read-only, takes no inputs, and shares its description with our own agent
  (`app/agent.py`), so the two cannot drift apart.

## Try it with our own client

```bash
python -m app.try_mcp
```

It starts the server, lists the tools (discovery), and calls `get_weather`.

## Connect it to Claude Desktop or Claude Code

These steps were **not tested against those apps** from the build environment: only against the
official MCP Python client. Check each app's current documentation if the syntax differs.

Use the project's own Python, so no secrets from `.env` are passed to the server (it needs none).

**Claude Desktop**, in its MCP configuration file:

```json
{
  "mcpServers": {
    "myday-weather": {
      "command": "/Users/YOUR_NAME/git-repo/myday-agent/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "env": { "PYTHONPATH": "/Users/YOUR_NAME/git-repo/myday-agent" }
    }
  }
}
```

**Claude Code**:

```bash
claude mcp add myday-weather -e PYTHONPATH=/Users/YOUR_NAME/git-repo/myday-agent -- /Users/YOUR_NAME/git-repo/myday-agent/.venv/bin/python -m app.mcp_server
```

Then ask: "Do I need an umbrella today?" The client should offer to call `get_weather`.

## Security notes

- **Only connect MCP servers you trust or wrote yourself.** A server runs with your permissions.
- **Tool descriptions are part of the prompt.** A malicious server can use them to steer the model.
  Treat descriptions from other people's servers as untrusted input (Lab 7 tests this).
- The SDK hides details of unexpected errors from the client. Only a `ToolError` (a failure we
  expect, such as "weather not available") sends its message across.
- Never print to stdout in the server: it would corrupt the protocol. Logs go to stderr.
