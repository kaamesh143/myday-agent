from types import SimpleNamespace

import pytest

from app.claude_client import MODEL, ClaudeRefusedError, ask_claude, estimate_cost_usd


def fake_client(*, text="Hello!", stop_reason="end_turn", input_tokens=12, output_tokens=5, extra_blocks=()):
    """A stand-in for the Anthropic client. It records the request and returns a fixed reply."""
    calls: list[dict] = []
    blocks = [*extra_blocks, SimpleNamespace(type="text", text=text)]
    response = SimpleNamespace(
        content=blocks,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )

    def create(**kwargs):
        calls.append(kwargs)
        return response

    return SimpleNamespace(messages=SimpleNamespace(create=create)), calls


def test_returns_text_and_token_counts():
    client, _ = fake_client(text="Hi there", input_tokens=25, output_tokens=7)
    reply = ask_claude(client, "Say hi")
    assert reply.text == "Hi there"
    assert (reply.input_tokens, reply.output_tokens) == (25, 7)
    assert reply.truncated is False


def test_sends_model_prompt_and_limit():
    client, calls = fake_client()
    ask_claude(client, "Say hi", max_tokens=50)
    assert calls[0]["model"] == MODEL
    assert calls[0]["max_tokens"] == 50
    assert calls[0]["messages"] == [{"role": "user", "content": "Say hi"}]
    assert "system" not in calls[0]


def test_system_prompt_is_sent_when_given():
    client, calls = fake_client()
    ask_claude(client, "Say hi", system="Reply in English.")
    assert calls[0]["system"] == "Reply in English."


def test_cut_off_reply_is_flagged():
    client, _ = fake_client(stop_reason="max_tokens", output_tokens=20)
    assert ask_claude(client, "Say hi", max_tokens=20).truncated is True


def test_ignores_non_text_blocks():
    thinking = SimpleNamespace(type="thinking", thinking="")
    client, _ = fake_client(text="Answer", extra_blocks=(thinking,))
    assert ask_claude(client, "Say hi").text == "Answer"


def test_refusal_raises():
    client, _ = fake_client(stop_reason="refusal")
    with pytest.raises(ClaudeRefusedError):
        ask_claude(client, "Say hi")


def test_cost_matches_haiku_prices():
    # 1,500 input tokens at $0.10/M plus 300 output tokens at $0.50/M
    assert estimate_cost_usd(1500, 300) == pytest.approx(0.0003)
