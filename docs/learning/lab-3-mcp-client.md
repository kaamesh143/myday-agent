# Lab 3: the bot becomes an MCP client

In Lab 2 we wrapped the weather tool in an MCP **server** (`app/mcp_server.py`).
Until now only other apps (Claude Desktop, Claude Code) used it. Our own bot still
called `get_weather_lines()` directly. In this lab the bot uses its own server.

## The picture

```
/myday or the agent
   │
   ▼
app/mcp_weather.py  (MCP client)
   │ 1. start server:  python -m app.mcp_server   (subprocess, stdio, no port)
   │ 2. list_tools  → is "get_weather" there?      (discovery)
   │ 3. call_tool("get_weather")                    (the SERVER runs the code)
   ▼
app/mcp_server.py  ──►  app/weather.py  ──►  Open-Meteo
```

If steps 1–3 break, `mcp_weather.py` falls back to calling `weather.py` directly.

## DevOps way to think about it

| MCP idea | You already know it as |
|---|---|
| stdio transport | A Jenkins agent launched over SSH: the controller starts it and talks over its stdin/stdout |
| `list_tools` (discovery) | A health/readiness check plus "what endpoints do you expose?" |
| Fallback to direct call | A circuit breaker / degraded mode: the service stays up when a dependency is down |
| Timeout (30 s) | `timeout:` on a pipeline step, so one hung call cannot block the whole job |

## Two kinds of failure (the main lesson)

| What failed | Example | What we do |
|---|---|---|
| **MCP itself** | server will not start, tool missing, timeout, odd reply | Fall back to the direct call |
| **The tool's work** | Open-Meteo is down, server answers `is_error=True` | Raise `WeatherError`, **no** fallback |

Why no fallback in the second case? The direct call would hit the same broken
weather service, so it would only double the waiting time. Retrying the wrong
layer is a classic incident mistake.

## Switch it on or off

In `.env`:

```bash
WEATHER_VIA_MCP=true   # default: use the MCP server, direct call as fallback
WEATHER_VIA_MCP=false  # old behaviour: call weather.py directly
```

The bot logs which one it uses at start-up (`Weather source: ...`).

## Try it

```bash
docker compose build
docker compose run --rm bot python -m app.try_mcp                       # Lab 2 client, step by step
docker compose run --rm bot python -m app.try_agent --mcp "Umbrella today?"  # agent, tool over MCP
docker compose run --rm bot python -m app.try_agent "Umbrella today?"        # agent, direct tool
```

Claude sees **the same tool** in both agent runs (same name, description, inputs).
Only where our code gets the answer changes. That is the point of MCP: the
model does not care where the tool lives.

## Things worth noticing

- **The server does not get your secrets.** The MCP SDK starts the subprocess with
  only `HOME`, `PATH`, `SHELL` and `TERM`. `TELEGRAM_BOT_TOKEN` and `ANTHROPIC_API_KEY`
  are not passed on. That is least privilege by default. One side effect: proxy
  settings (`HTTPS_PROXY`) are not passed either. If you ever run the bot behind a
  proxy, pass `env=` in `StdioServerParameters`.
- **Cost of a subprocess.** Each `/myday` starts a fresh Python process (about 1 s).
  Fine for a few calls a day. For many calls you would keep one session open.
- **`asyncio.run` inside a running loop fails.** The MCP client is async. The bot's
  handlers already use `asyncio.to_thread`, so the call runs in a thread with its own loop.

## Tests

`tests/test_mcp_weather.py`. Most tests connect the client to the server **in memory**
(pass the server object instead of a command), so they are fast and need no network.
One test starts the real subprocess, with its proxy pointed at a closed port, to prove the
whole stdio path works and that a weather failure comes back as a clean error.

## Self-check (answer without AI)

1. Where does the weather code actually run when `WEATHER_VIA_MCP=true`: in the bot process or another process?
2. Why does a `WeatherError` from the server not trigger the fallback?
3. What would you see in the logs if `app/mcp_server.py` had a syntax error?
4. Name one secret that the MCP server process cannot read, and why.
