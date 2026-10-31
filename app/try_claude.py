"""Manual check: ask Claude one question and print the reply, tokens and cost.

Run it with: docker compose run --rm bot python -m app.try_claude "Say hello"
"""

import sys

import anthropic

from app.claude_client import ask_claude


def main() -> None:
    prompt = " ".join(sys.argv[1:]) or "Say hello in one short sentence."
    reply = ask_claude(anthropic.Anthropic(), prompt, max_tokens=200)
    print(reply.text)
    print(f"\ninput tokens: {reply.input_tokens}, output tokens: {reply.output_tokens}")
    print(f"cost: ${reply.cost_usd:.6f}, cut off: {reply.truncated}")


if __name__ == "__main__":
    main()
