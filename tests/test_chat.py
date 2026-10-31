import asyncio
from types import SimpleNamespace

import anthropic
import httpx

from app.bot import chat, log_unauthorized
from app.chat import MAX_INPUT_CHARS, SYSTEM_PROMPT, answer


def make_client(*, text="Hello!", stop_reason="end_turn", error=None):
    """A stand-in for the Anthropic client that records requests."""
    calls: list[dict] = []
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )

    def create(**kwargs):
        calls.append(kwargs)
        if error:
            raise error
        return response

    return SimpleNamespace(messages=SimpleNamespace(create=create)), calls


def test_answer_returns_claude_text():
    client, calls = make_client(text="Good morning")
    assert answer(client, "hi") == "Good morning"
    assert calls[0]["system"] == SYSTEM_PROMPT


def test_answer_adds_note_when_cut_off():
    client, _ = make_client(text="Part of an answer", stop_reason="max_tokens")
    result = answer(client, "hi")
    assert result.startswith("Part of an answer")
    assert "cut off" in result


def test_answer_handles_refusal():
    client, _ = make_client(stop_reason="refusal")
    assert "declined" in answer(client, "hi")


def test_answer_handles_api_error_without_crashing():
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))
    client, _ = make_client(error=error)
    assert "not available" in answer(client, "hi")


def test_answer_handles_empty_reply():
    client, _ = make_client(text="")
    assert "empty" in answer(client, "hi")


def test_too_long_message_never_reaches_claude():
    client, calls = make_client()
    result = answer(client, "x" * (MAX_INPUT_CHARS + 1))
    assert "too long" in result
    assert calls == []


def test_handler_replies_with_claude_answer():
    client, _ = make_client(text="Hi from Claude")
    actions: list[str] = []
    replies: list[str] = []

    class FakeChat:
        async def send_action(self, action):
            actions.append(action)

    class FakeMessage:
        text = "hello"
        chat = FakeChat()

        async def reply_text(self, text):
            replies.append(text)

    update = SimpleNamespace(message=FakeMessage())
    context = SimpleNamespace(bot_data={"claude": client})
    asyncio.run(chat(update, context))
    assert replies == ["Hi from Claude"]
    assert len(actions) == 1


def run_log_unauthorized(user_id, allowed):
    update = SimpleNamespace(effective_user=SimpleNamespace(id=user_id, username=None))
    context = SimpleNamespace(bot_data={"allowed_user_ids": frozenset(allowed)})
    asyncio.run(log_unauthorized(update, context))


def test_allowed_user_is_not_logged_as_unauthorized(caplog):
    with caplog.at_level("WARNING", logger="assistant"):
        run_log_unauthorized(42, {42})
    assert "unauthorized" not in caplog.text


def test_stranger_is_logged_as_unauthorized(caplog):
    with caplog.at_level("WARNING", logger="assistant"):
        run_log_unauthorized(99, {42})
    assert "unauthorized user id=99" in caplog.text
