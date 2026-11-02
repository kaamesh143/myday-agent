"""Logging settings shared by the bot and the MCP server."""

import logging

# httpx logs the full URL of every request. Telegram URLs contain the bot token, and weather
# URLs contain the owner's coordinates, so these loggers only speak up for warnings and errors.
# httpx2 is the name used by the Anthropic library.
NOISY_HTTP_LOGGERS = ("httpx", "httpx2", "httpcore", "httpcore2")


def quiet_http_logs() -> None:
    for name in NOISY_HTTP_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
