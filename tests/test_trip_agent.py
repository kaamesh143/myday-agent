import asyncio
import json
from types import SimpleNamespace

import app.trip_agent as trip_agent
from app.bot import chat
from app.gmail_source import Attachment
from app.trip import NOT_CONNECTED, TripConfig, TripItem
from tests.test_agent import ScriptedClient, reply, text_block, tool_block

# Synthetic data only.
PDF = Attachment("ticket.pdf", "Your e-ticket XY 101", b"%PDF fake")
FLIGHT = TripItem("flight", "XY 101 Copenhagen → Dubai", "2099-11-20", "10:35", reference="ABC123")


def config(tmp_path):
    return TripConfig(tmp_path / "token.json", tmp_path / "cache.json", "Europe/Stockholm")


def tool_names(client):
    return [tool["name"] for tool in client.requests[0]["tools"]]


def test_plain_question_can_use_the_trip_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(trip_agent, "load_trip_items", lambda cfg, client: [FLIGHT])
    client = ScriptedClient(
        [
            reply([tool_block("get_trip_plan", "t1")], "tool_use"),
            reply([text_block("Your flight XY 101 leaves at 10:35.")], "end_turn"),
        ]
    )
    result = trip_agent.answer_with_tools(client, "what is my plan on 20 Nov?", config(tmp_path))
    assert result.text == "Your flight XY 101 leaves at 10:35."
    assert {"get_weather", "get_trip_plan", "find_booking_documents"} <= set(tool_names(client))
    sent_back = client.requests[1]["messages"][-1]["content"][0]["content"]
    assert json.loads(sent_back)[0]["reference"] == "ABC123"
    assert "never say you cannot access email" in client.requests[0]["system"].lower()


def test_booking_request_collects_pdfs_to_send(monkeypatch, tmp_path):
    seen = {}

    def fake_find(cfg, words):
        seen["words"] = words
        return [PDF]

    monkeypatch.setattr(trip_agent, "find_ticket_pdfs", fake_find)
    client = ScriptedClient(
        [
            reply([tool_block("find_booking_documents", "t1", {"words": "XY 101"})], "tool_use"),
            reply([text_block("Your ticket is on its way.")], "end_turn"),
        ]
    )
    result = trip_agent.answer_with_tools(client, "share my flight ticket pdf", config(tmp_path))
    assert result.pdfs == [PDF]
    assert seen["words"] == "XY 101"


def test_tool_messages_are_passed_back_to_claude(monkeypatch, tmp_path):
    monkeypatch.setattr(trip_agent, "load_trip_items", lambda cfg, client: NOT_CONNECTED)
    client = ScriptedClient(
        [
            reply([tool_block("get_trip_plan", "t1")], "tool_use"),
            reply([text_block("Please sign in again.")], "end_turn"),
        ]
    )
    trip_agent.answer_with_tools(client, "my plan?", config(tmp_path))
    assert "not connected" in client.requests[1]["messages"][-1]["content"][0]["content"]


def test_empty_and_too_long_messages_never_reach_claude(tmp_path):
    client = ScriptedClient([])
    assert "some text" in trip_agent.answer_with_tools(client, "   ", config(tmp_path)).text
    assert "too long" in trip_agent.answer_with_tools(client, "x" * 5000, config(tmp_path)).text
    assert client.requests == []


def test_chat_handler_sends_answer_then_pdfs(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.bot.answer_with_tools", lambda client, text, cfg: trip_agent.ChatResult("Here it is.", [PDF])
    )
    sent = []

    class FakeChat:
        async def send_action(self, action):
            pass

    class FakeMessage:
        text = "send my ticket"
        chat = FakeChat()

        async def reply_text(self, text):
            sent.append(text)

        async def reply_document(self, document, filename, caption):
            sent.append(filename)

    context = SimpleNamespace(bot_data={"claude": None, "trip_config": config(tmp_path)})
    asyncio.run(chat(SimpleNamespace(message=FakeMessage()), context))
    assert sent == ["Here it is.", "ticket.pdf"]
