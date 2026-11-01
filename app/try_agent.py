"""Manual check: watch the agent loop step by step.

Run it with: docker compose run --rm bot python -m app.try_agent "Do I need an umbrella today?"
"""

import sys

import anthropic

from app.agent import WEATHER_TOOL, run_agent


def main() -> None:
    question = " ".join(sys.argv[1:]) or "Do I need an umbrella today?"
    result = run_agent(anthropic.Anthropic(), question, [WEATHER_TOOL])

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
