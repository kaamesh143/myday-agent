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

## Lab 3: the bot as an MCP client

Until now only other apps used the server. The bot itself still called `app/weather.py` directly.
In Lab 3 the bot can ask the server instead, exactly like Claude Desktop does.

```
/myday (app/myday.py)
   │  WEATHER_SOURCE=mcp
   ▼
MCP client (app/mcp_weather_client.py)  ── starts ──▶  MCP server (app/mcp_server.py)
   │                                                     └─ runs get_weather → Open-Meteo
   │  MCP broke? (did not start, timed out, odd reply)
   ▼
direct call (app/weather.py)  ← fallback, same as before Lab 3
```

### Turn it on

Add one line to `.env`, then restart the bot:

```bash
WEATHER_SOURCE=mcp
docker compose up -d --build
docker compose logs bot | grep "Weather for /myday"   # should say: mcp
```

Send `/myday`. The reply looks the same as before: only the route behind it changed.

### How failures are handled

| What went wrong | Example | What /myday does |
|---|---|---|
| MCP itself broke | server crashed, no reply in 30 s | logs a warning, uses the direct call |
| Weather service down | Open-Meteo unreachable | shows "Weather is not available right now." (no second try: the direct call would hit the same service) |

### Things to know

- **Cost per /myday:** a new Python process starts each time (about 1 to 2 seconds). Fine for a few
  messages a day. A long-running bot that calls tools often would keep one connection open instead.
- **No secrets reach the server.** The client passes no environment, so the SDK gives the
  subprocess only `HOME`, `PATH`, `SHELL` and `TERM`. The weather server needs nothing else.
- **Worst-case wait:** if MCP hangs for the full 30 s and then the direct call also struggles,
  /myday can take about 50 s. It runs in a thread, so the bot stays responsive meanwhile.

### Roll back

Set `WEATHER_SOURCE=direct` (or delete the line) and restart. Nothing else changes: the direct call
is the same code as before Lab 3.
