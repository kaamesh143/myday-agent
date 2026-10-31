"""Turn a Telegram message into a Claude answer, with friendly error handling."""

import logging

import anthropic

from app.claude_client import ClaudeRefusedError, ask_claude

log = logging.getLogger("assistant")

SYSTEM_PROMPT = (
    "You are a personal assistant in a private Telegram chat with its owner. "
    "Reply in clear, simple English and keep answers short. "
    "If you do not know something, say so. "
    "You cannot access the owner's calendar, email or files."
)
MAX_TOKENS = 700
MAX_INPUT_CHARS = 4000  # keeps the cost of one message small
TELEGRAM_LIMIT = 4000  # Telegram allows 4096 characters per message


def answer(client: anthropic.Anthropic, text: str) -> str:
    """Return the text to send back to the user. Never raises for Claude problems."""
    if len(text) > MAX_INPUT_CHARS:
        return f"That message is too long ({len(text)} characters). Please keep it under {MAX_INPUT_CHARS}."
    try:
        reply = ask_claude(client, text, system=SYSTEM_PROMPT, max_tokens=MAX_TOKENS)
    except ClaudeRefusedError:
        return "Claude declined to answer that request."
    except anthropic.APIError as exc:
        # Log only the error type, never the message text.
        log.warning("Claude API call failed: %s", type(exc).__name__)
        return "Claude is not available right now. Please try again in a minute."

    # Log counts and cost only, never the message text.
    log.info(
        "Claude reply: input=%d output=%d cost=$%.6f cut_off=%s",
        reply.input_tokens,
        reply.output_tokens,
        reply.cost_usd,
        reply.truncated,
    )
    if not reply.text:
        return "Claude returned an empty answer. Please try again."
    result = reply.text[:TELEGRAM_LIMIT]
    if reply.truncated:
        result += "\n\n(This answer was cut off because it reached the length limit.)"
    return result
