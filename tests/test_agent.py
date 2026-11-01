from types import SimpleNamespace

import pytest

from app.agent import Tool, run_agent
from app.claude_client import ClaudeRefusedError
from app.weather import WeatherError


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(name="get_weather", tool_id="toolu_1", arguments=None):
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=arguments or {})


def reply(blocks, stop_reason, input_tokens=10, output_tokens=5):
    return SimpleNamespace(
        content=blocks,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class ScriptedClient:
    """Plays back a fixed list of replies and records each request it receives."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        # Copy the message list: the agent keeps appending to the real one.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return self._replies.pop(0)


def weather_tool(run=lambda arguments: "Dry and calm all day.\nMax 11° / Min 8°."):
    return Tool(name="get_weather", description="Weather.", input_schema={"type": "object"}, run=run)


def test_answers_directly_when_no_tool_is_needed():
    client = ScriptedClient([reply([text_block("Hello!")], "end_turn")])
    result = run_agent(client, "hi", [weather_tool()])
    assert result.text == "Hello!"
    assert result.steps == ()
    assert result.stopped_reason == "end_turn"
    assert len(client.requests) == 1


def test_tool_round_trip_sends_result_back_and_returns_final_answer():
    first = reply([text_block("Let me check."), tool_block(tool_id="toolu_9")], "tool_use", 20, 8)
    second = reply([text_block("No umbrella needed.")], "end_turn", 40, 6)
    client = ScriptedClient([first, second])

    result = run_agent(client, "Umbrella today?", [weather_tool()])

    assert result.text == "No umbrella needed."
    assert [step.tool for step in result.steps] == ["get_weather"]
    assert result.steps[0].result.startswith("Dry and calm")
    assert (result.input_tokens, result.output_tokens) == (60, 14)

    second_request = client.requests[1]["messages"]
    assert second_request[1] == {"role": "assistant", "content": first.content}
    tool_results = second_request[2]["content"]
    assert tool_results == [
        {
            "type": "tool_result",
            "tool_use_id": "toolu_9",
            "content": "Dry and calm all day.\nMax 11° / Min 8°.",
            "is_error": False,
        }
    ]


def test_tool_definitions_are_sent_without_the_run_function():
    client = ScriptedClient([reply([text_block("Hi")], "end_turn")])
    run_agent(client, "hi", [weather_tool()])
    assert client.requests[0]["tools"] == [
        {"name": "get_weather", "description": "Weather.", "input_schema": {"type": "object"}}
    ]


def test_tool_failure_is_reported_to_claude_as_an_error():
    def broken(arguments):
        raise WeatherError("Weather is not available right now.")

    client = ScriptedClient(
        [reply([tool_block()], "tool_use"), reply([text_block("Sorry, no weather.")], "end_turn")]
    )
    result = run_agent(client, "Umbrella?", [weather_tool(broken)])
    assert result.steps[0].is_error is True
    assert client.requests[1]["messages"][2]["content"][0]["is_error"] is True
    assert result.text == "Sorry, no weather."


def test_unexpected_tool_error_does_not_leak_details_to_claude():
    def broken(arguments):
        raise RuntimeError("secret internal detail")

    client = ScriptedClient([reply([tool_block()], "tool_use"), reply([text_block("Done")], "end_turn")])
    result = run_agent(client, "Umbrella?", [weather_tool(broken)])
    assert result.steps[0].result == "The tool failed."
    assert "secret" not in str(client.requests[1]["messages"][2])


def test_unknown_tool_gets_an_error_result():
    client = ScriptedClient(
        [reply([tool_block(name="delete_everything")], "tool_use"), reply([text_block("Ok")], "end_turn")]
    )
    result = run_agent(client, "hi", [weather_tool()])
    assert result.steps[0].is_error is True
    assert "Unknown tool" in result.steps[0].result


def test_several_tool_requests_are_answered_in_one_message():
    blocks = [tool_block(tool_id="a"), tool_block(tool_id="b")]
    client = ScriptedClient([reply(blocks, "tool_use"), reply([text_block("Both done")], "end_turn")])
    result = run_agent(client, "hi", [weather_tool()])
    assert len(result.steps) == 2
    answered = [item["tool_use_id"] for item in client.requests[1]["messages"][2]["content"]]
    assert answered == ["a", "b"]


def test_step_limit_stops_a_loop_that_never_ends():
    endless = [reply([tool_block()], "tool_use") for _ in range(10)]
    client = ScriptedClient(endless)
    result = run_agent(client, "hi", [weather_tool()], max_steps=2)
    assert result.stopped_reason == "max_steps"
    assert len(result.steps) == 2
    assert len(client.requests) == 3  # two tool rounds, then one last call that is not followed


def test_cut_off_final_answer_is_flagged():
    client = ScriptedClient([reply([text_block("Half an ans")], "max_tokens")])
    result = run_agent(client, "hi", [weather_tool()])
    assert result.truncated is True
    assert result.stopped_reason == "max_tokens"


def test_refusal_raises():
    client = ScriptedClient([reply([], "refusal")])
    with pytest.raises(ClaudeRefusedError):
        run_agent(client, "hi", [weather_tool()])


def test_thinking_blocks_are_passed_back_unchanged():
    thinking = SimpleNamespace(type="thinking", thinking="")
    first = reply([thinking, tool_block()], "tool_use")
    client = ScriptedClient([first, reply([text_block("Done")], "end_turn")])
    run_agent(client, "hi", [weather_tool()])
    assert client.requests[1]["messages"][1]["content"] is first.content
