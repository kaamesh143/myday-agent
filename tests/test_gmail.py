import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.google_token as google_token
from app.gmail_source import (
    GmailNotAllowedError,
    body_text,
    build_gmail_service,
    fetch_booking_emails,
    html_to_text,
    parse_message,
)
from app.google_token import ALL_SCOPES, CALENDAR_SCOPE, GMAIL_SCOPE, load_credentials

# Synthetic data only: no real bookings.


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def message(subject="Your booking ABC123", plain=None, html=None):
    parts = []
    if plain is not None:
        parts.append({"mimeType": "text/plain", "body": {"data": b64(plain)}})
    if html is not None:
        parts.append({"mimeType": "text/html", "body": {"data": b64(html)}})
    return {
        "snippet": "snippet text",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": "Example Air <no-reply@example.com>"},
                {"name": "Date", "value": "Mon, 2 Nov 2026 10:00:00 +0100"},
            ],
            "parts": parts,
        },
    }


def test_plain_text_is_preferred_over_html():
    payload = message(plain="Flight XY 123", html="<b>ignored</b>")["payload"]
    assert body_text(payload) == "Flight XY 123"


def test_html_is_turned_into_text():
    raw = "<style>p{}</style><table><tr><td>Flight</td><td>XY&nbsp;123</td></tr></table><p>Seat 12A</p>"
    text = html_to_text(raw)
    assert "Flight" in text and "XY" in text and "Seat 12A" in text
    assert "<" not in text and "p{}" not in text


def test_parse_message_reads_headers_and_falls_back_to_snippet():
    email = parse_message(message(plain=None, html=None))
    assert email.subject == "Your booking ABC123"
    assert email.sender.startswith("Example Air")
    assert email.text == "snippet text"


def test_long_bodies_are_cut():
    email = parse_message(message(plain="x" * 10_000))
    assert len(email.text) == 3500


def fake_gmail(messages_by_id):
    calls = []

    def list_(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(execute=lambda: {"messages": [{"id": i} for i in messages_by_id]})

    def get(**kwargs):
        return SimpleNamespace(execute=lambda: messages_by_id[kwargs["id"]])

    msgs = SimpleNamespace(list=list_, get=get)
    return SimpleNamespace(users=lambda: SimpleNamespace(messages=lambda: msgs)), calls


def test_fetch_uses_the_query_and_reads_every_message(tmp_path):
    service, calls = fake_gmail({"a": message(plain="one"), "b": message(plain="two")})
    emails = fetch_booking_emails(tmp_path / "t.json", "subject:ticket", service_factory=lambda p: service)
    assert [e.text for e in emails] == ["one", "two"]
    assert calls[0]["q"] == "subject:ticket"
    assert calls[0]["userId"] == "me"


def test_no_matches_means_empty_list(tmp_path):
    service, _ = fake_gmail({})
    assert fetch_booking_emails(tmp_path / "t.json", service_factory=lambda p: service) == []


def write_token(path, scopes):
    path.write_text(
        json.dumps(
            {
                "token": "fake-access",
                "refresh_token": "fake-refresh",
                "client_id": "fake.apps.googleusercontent.com",
                "client_secret": "fake",
                "scopes": scopes,
                "expiry": "2999-01-01T00:00:00Z",
            }
        )
    )


def test_old_calendar_only_token_is_not_allowed_to_read_gmail(tmp_path):
    token = tmp_path / "token.json"
    write_token(token, [CALENDAR_SCOPE])
    with pytest.raises(GmailNotAllowedError):
        build_gmail_service(token)


def test_token_keeps_every_approved_scope(tmp_path):
    token = tmp_path / "token.json"
    write_token(token, ALL_SCOPES)
    credentials = load_credentials(token)
    assert google_token.has_scope(credentials, GMAIL_SCOPE)
    assert google_token.has_scope(credentials, CALENDAR_SCOPE)


def test_only_read_only_scopes_are_requested():
    assert all(scope.endswith(".readonly") for scope in ALL_SCOPES)


def pdf_message(parts):
    return {
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [{"name": "Subject", "value": "Booking confirmation 123"}],
            "parts": [{"mimeType": "text/plain", "body": {"data": b64("hi")}}, *parts],
        }
    }


def fake_gmail_with_attachments(messages_by_id, attachments):
    calls = []

    def list_(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(execute=lambda: {"messages": [{"id": i} for i in messages_by_id]})

    def get(**kwargs):
        return SimpleNamespace(execute=lambda: messages_by_id[kwargs["id"]])

    def get_attachment(**kwargs):
        return SimpleNamespace(execute=lambda: {"data": attachments[kwargs["id"]]})

    msgs = SimpleNamespace(list=list_, get=get, attachments=lambda: SimpleNamespace(get=get_attachment))
    return SimpleNamespace(users=lambda: SimpleNamespace(messages=lambda: msgs)), calls


def test_pdf_attachments_are_downloaded_and_named():
    from app.gmail_source import fetch_pdf_attachments

    pdf_body = {"attachmentId": "a1", "size": 9}
    part = {"filename": "booking.pdf", "mimeType": "application/pdf", "body": pdf_body}
    image = {"filename": "logo.png", "mimeType": "image/png", "body": {"attachmentId": "a2", "size": 9}}
    service, calls = fake_gmail_with_attachments(
        {"m1": pdf_message([part, image])}, {"a1": b64("%PDF-1.4 fake")}
    )
    pdfs = fetch_pdf_attachments(Path("t.json"), "Scandic", service_factory=lambda p: service)
    assert [(p.filename, p.subject, p.data) for p in pdfs] == [
        ("booking.pdf", "Booking confirmation 123", b"%PDF-1.4 fake")
    ]
    assert "has:attachment filename:pdf" in calls[0]["q"] and "Scandic" in calls[0]["q"]


def test_at_most_three_pdfs_and_huge_ones_are_skipped():
    from app.gmail_source import fetch_pdf_attachments

    huge = {"filename": "big.pdf", "body": {"attachmentId": "x", "size": 10**9}}
    small = [{"filename": f"t{n}.pdf", "body": {"data": b64("pdf"), "size": 3}} for n in range(5)]
    service, _ = fake_gmail_with_attachments({"m1": pdf_message([huge, *small])}, {})
    pdfs = fetch_pdf_attachments(Path("t.json"), "x", service_factory=lambda p: service)
    assert [p.filename for p in pdfs] == ["t0.pdf", "t1.pdf", "t2.pdf"]
