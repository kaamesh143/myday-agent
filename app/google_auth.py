"""One-time Google sign-in. Run it on your own computer, not in Docker.

It opens your browser, asks for READ-ONLY access to your calendar, and saves a token file.
Run: python -m app.google_auth
"""

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from app.calendar_source import SCOPES


def main() -> None:
    credentials_file = Path(os.environ.get("GOOGLE_CREDENTIALS_FILE", "data/credentials.json"))
    token_file = Path(os.environ.get("GOOGLE_TOKEN_FILE", "data/token.json"))
    if not credentials_file.exists():
        raise SystemExit(f"{credentials_file} not found. Download the OAuth client file there first.")

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
    # offline + consent make Google give us a refresh token, so the bot stays signed in.
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json())
    token_file.chmod(0o600)  # the token is a secret: only your user may read it
    print(f"Saved read-only calendar token to {token_file}. Never share or commit this file.")


if __name__ == "__main__":
    main()
