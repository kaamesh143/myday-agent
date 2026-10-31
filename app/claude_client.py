"""Ask Claude a question and get back the reply, the token counts and the cost."""

from dataclasses import dataclass
from typing import Any

import anthropic

MODEL = "claude-haiku-5-5"

# Haiku 5.5 prices in US dollars per million tokens (for prompts up to 100K tokens).
INPUT_USD_PER_MTOK = 0.10
OUTPUT_USD_PER_MTOK = 0.50


class ClaudeRefusedError(Exception):
    """Claude declined to answer (stop_reason is "refusal")."""


@dataclass(frozen=True)
class ClaudeReply:
    text: str
    input_tokens: int
    output_tokens: int
    truncated: bool  # True when the reply hit max_tokens and was cut off

    @property
    def cost_usd(self) -> float:
        return estimate_cost_usd(self.input_tokens, self.output_tokens)


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Cost in US dollars of one request, from its token counts."""
    return (input_tokens * INPUT_USD_PER_MTOK + output_tokens * OUTPUT_USD_PER_MTOK) / 1_000_000


def ask_claude(
    client: anthropic.Anthropic,
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = 1024,
) -> ClaudeReply:
    """Send one prompt to Claude and return its reply.

    Raises ClaudeRefusedError if Claude declines. Network and API errors from
    the SDK are not caught here: the caller decides how to handle them.
    """
    request: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system is not None:
        request["system"] = system

    response = client.messages.create(**request)

    if response.stop_reason == "refusal":
        raise ClaudeRefusedError("Claude declined to answer this request.")

    # The reply is a list of blocks. Keep only the text blocks.
    text = "".join(block.text for block in response.content if block.type == "text")
    return ClaudeReply(
        text=text,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        truncated=response.stop_reason == "max_tokens",
    )
