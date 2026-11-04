"""Manual check: watch the agent loop step by step.

Run it with: docker compose run --rm bot python -m app.try_agent "Do I need an umbrella today?"
Add --mcp to get the weather through our MCP server instead (Lab 3).
"""

import sys

import anthropic

from app.agent import MCP_WEATHER_TOOL, WEATHER_TOOL, run_agent


def main() -> None:
    arguments = sys.argv[1:]
    use_mcp = "--mcp" in arguments
    question = " ".join(word for word in arguments if word != "--mcp") or "Do I need an umbrella today?"
    tool = MCP_WEATHER_TOOL if use_mcp else WEATHER_TOOL
    result = run_agent(anthropic.Anthropic(), question, [tool])

    print(f"Weather tool runs: {'through the MCP server' if use_mcp else 'directly in this process'}")

    print(f"Question: {question}\n")
    if not result.steps:
        print("Claude answered without using any tool.")
    for number, step in enumerate(result.steps, start=1):
        print(f"Step {number}: Claude asked for the tool '{step.tool}' with arguments {step.arguments}")
        print(f"  Our code ran it. Result sent back (error={step.is_error}):")
        for line in step.result.splitlines():
            print(f"    {line}")
    print(f"\nFinal answer: {result.text}")
    print(f"\nTokens: {result.input_tokens} in, {result.output_tokens} out")
    print(f"Cost: ${result.cost_usd:.6f}  Stopped because: {result.stopped_reason}")


if __name__ == "__main__":
    main()
