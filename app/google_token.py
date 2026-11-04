"""Load the saved Google token and keep it fresh. Shared by the calendar and Gmail readers.

The token remembers which scopes you approved. We load it with exactly those scopes,
so refreshing it for the calendar never drops the Gmail permission (or the other way round).
"""

from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
# What the one-time sign-in asks for. Both are read-only: the bot can never change or send anything.
ALL_SCOPES = [CALENDAR_SCOPE, GMAIL_SCOPE]


def load_credentials(token_path: Path) -> Credentials:
    """Read token.json, refresh it when it has expired, and save the refreshed token."""
    credentials = Credentials.from_authorized_user_file(str(token_path))
    if not credentials.valid:
        if not credentials.refresh_token:
            raise RefreshError("The saved token cannot be refreshed.")
        credentials.refresh(Request())
        token_path.write_text(credentials.to_json())
        token_path.chmod(0o600)
    return credentials


def has_scope(credentials: Credentials, scope: str) -> bool:
    """True when the user approved this scope during sign-in."""
    return scope in (credentials.scopes or [])
