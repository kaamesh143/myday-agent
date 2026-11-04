"""Find travel booking emails in Gmail (read-only) and return their text.

We only read. The scope is gmail.readonly, so the bot cannot send, delete or label anything.
Email bodies are never logged.
"""

import base64
import html
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build

from app.google_token import GMAIL_SCOPE, has_scope, load_credentials

log = logging.getLogger("assistant")

# Booking emails from the last 6 months. Bookings are often made long before the trip.
# Override with TRIP_GMAIL_QUERY in .env (same syntax as the Gmail search box).
DEFAULT_QUERY = (
    "newer_than:180d -category:promotions -category:social "
    "subject:(booking OR booked OR ticket OR e-ticket OR itinerary OR reservation "
    'OR confirmation OR confirmed OR "boarding pass" OR flight OR train OR hotel)'
)
MAX_EMAILS = 15
MAX_CHARS_PER_EMAIL = 3500  # keeps one Claude request small and cheap


class GmailNotAllowedError(Exception):
    """The saved token does not include Gmail read access yet (sign in again)."""


@dataclass(frozen=True)
class Email:
    subject: str
    sender: str
    date: str  # as written in the Date header
    text: str


def build_gmail_service(token_path: Path) -> Any:
    """Open the Gmail API, or raise GmailNotAllowedError if the sign-in did not include Gmail."""
    credentials = load_credentials(token_path)
    if not has_scope(credentials, GMAIL_SCOPE):
        raise GmailNotAllowedError("Gmail read access was not approved yet.")
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _decode(data: str) -> str:
    # Gmail sends bodies as URL-safe base64, sometimes without padding.
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def html_to_text(raw: str) -> str:
    """A rough HTML to text conversion. Good enough for Claude to read a booking."""
    raw = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", raw)
    raw = re.sub(r"(?i)</t[dh]>", " | ", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(raw)


def tidy(text: str) -> str:
    """Squash repeated spaces and blank lines."""
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def body_text(payload: dict[str, Any]) -> str:
    """The readable text of one message: plain text if present, otherwise converted HTML."""
    plain: list[str] = []
    rich: list[str] = []

    def walk(part: dict[str, Any]) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            rich.append(html_to_text(_decode(data)))
        for child in part.get("parts", []):
            walk(child)

    walk(payload)
    return tidy("\n".join(plain) if plain else "\n".join(rich))


def parse_message(message: dict[str, Any]) -> Email:
    payload = message.get("payload", {})
    headers = {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", [])}
    text = body_text(payload) or message.get("snippet", "")
    return Email(
        subject=headers.get("subject", "(no subject)"),
        sender=headers.get("from", ""),
        date=headers.get("date", ""),
        text=text[:MAX_CHARS_PER_EMAIL],
    )


def fetch_booking_emails(
    token_path: Path,
    query: str = DEFAULT_QUERY,
    *,
    service_factory: Callable[[Path], Any] = build_gmail_service,
    max_emails: int = MAX_EMAILS,
) -> list[Email]:
    """Search Gmail and return the newest matching emails. Google errors pass through to the caller."""
    service = service_factory(token_path)
    messages = service.users().messages()
    found = messages.list(userId="me", q=query, maxResults=max_emails).execute()
    emails = [
        parse_message(messages.get(userId="me", id=item["id"], format="full").execute())
        for item in found.get("messages", [])
    ]
    log.info("Gmail: %d booking emails found", len(emails))  # a count only, never content
    return emails
