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
    "subject:(booking OR booked OR ticket OR e-ticket OR eticket OR itinerary OR reservation "
    'OR confirmation OR confirmed OR "boarding pass" OR flight OR train OR hotel '
    "OR trip OR journey OR travel OR receipt)"
)
# A trip has many emails (a hotel alone sent 9), so read enough to reach the flights too.
MAX_EMAILS = 40  # at most one email per Gmail conversation
MAX_CHARS_PER_EMAIL = 2500  # 40 x 2500 characters is about 25k tokens: under 1 cent with Haiku
MAX_PDFS = 3  # most PDFs /ticket sends for one request
MAX_PDF_BYTES = 20 * 1024 * 1024  # Telegram bots can send up to 50 MB; tickets are far smaller


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
    found = messages.list(userId="me", q=query, maxResults=max_emails * 3).execute()
    # Keep the newest email of each conversation: replies and reminders repeat the same booking.
    seen_threads: set[str] = set()
    ids = []
    for item in found.get("messages", []):
        thread = item.get("threadId", item["id"])
        if thread not in seen_threads:
            seen_threads.add(thread)
            ids.append(item["id"])
    emails = [
        parse_message(messages.get(userId="me", id=message_id, format="full").execute())
        for message_id in ids[:max_emails]
    ]
    log.info("Gmail: %d booking emails found", len(emails))  # a count only, never content
    return emails


@dataclass(frozen=True)
class Attachment:
    filename: str
    subject: str  # of the email it came from, so you can tell which booking it is
    data: bytes


def pdf_query(words: str) -> str:
    """Gmail search for emails from the last year that have a PDF and match your words."""
    return f"has:attachment filename:pdf newer_than:365d {words}".strip()


def pdf_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Every part of an email that is a PDF file."""
    found = []

    def walk(part: dict[str, Any]) -> None:
        name = part.get("filename") or ""
        if name.lower().endswith(".pdf") or (name and part.get("mimeType") == "application/pdf"):
            found.append(part)
        for child in part.get("parts", []):
            walk(child)

    walk(payload)
    return found


def fetch_pdf_attachments(
    token_path: Path,
    words: str,
    *,
    service_factory: Callable[[Path], Any] = build_gmail_service,
    max_pdfs: int = MAX_PDFS,
) -> list[Attachment]:
    """Find PDF attachments (newest emails first) in emails matching words. Google errors pass through."""
    service = service_factory(token_path)
    messages = service.users().messages()
    found = messages.list(userId="me", q=pdf_query(words), maxResults=5).execute()
    attachments: list[Attachment] = []
    for item in found.get("messages", []):
        message = messages.get(userId="me", id=item["id"], format="full").execute()
        payload = message.get("payload", {})
        headers = {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", [])}
        for part in pdf_parts(payload):
            body = part.get("body", {})
            if body.get("size", 0) > MAX_PDF_BYTES:
                continue
            data = body.get("data")
            if not data and body.get("attachmentId"):
                data = (
                    messages.attachments()
                    .get(userId="me", messageId=item["id"], id=body["attachmentId"])
                    .execute()
                    .get("data")
                )
            if not data:
                continue
            raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
            attachments.append(Attachment(part["filename"], headers.get("subject", ""), raw))
            if len(attachments) >= max_pdfs:
                log.info("Gmail: %d PDFs found", len(attachments))
                return attachments
    log.info("Gmail: %d PDFs found", len(attachments))  # a count only, never names or content
    return attachments


@dataclass(frozen=True)
class EmailLink:
    subject: str
    date: str
    url: str  # opens the email in Gmail (web or app)


def gmail_url(message_id: str) -> str:
    return f"https://mail.google.com/mail/u/0/#all/{message_id}"


def fetch_email_links(
    token_path: Path,
    words: str,
    *,
    service_factory: Callable[[Path], Any] = build_gmail_service,
    max_emails: int = 3,
) -> list[EmailLink]:
    """The newest emails matching words (no adverts), as subject, date and a Gmail link."""
    service = service_factory(token_path)
    messages = service.users().messages()
    query = f"newer_than:365d -category:promotions {words}".strip()
    found = messages.list(userId="me", q=query, maxResults=max_emails).execute()
    links = []
    for item in found.get("messages", []):
        message = messages.get(
            userId="me", id=item["id"], format="metadata", metadataHeaders=["Subject", "Date"]
        ).execute()
        payload = message.get("payload", {})
        headers = {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", [])}
        subject = headers.get("subject", "(no subject)")
        links.append(EmailLink(subject, headers.get("date", ""), gmail_url(item["id"])))
    return links
