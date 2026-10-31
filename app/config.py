"""Load settings from environment variables (.env in Docker)."""

import os
from dataclasses import dataclass


def parse_user_ids(raw: str) -> frozenset[int]:
    """Turn "123, 456" into {123, 456}. Ignores blanks; rejects non-numbers."""
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.lstrip("-").isdigit():
            raise ValueError(f"ALLOWED_USER_IDS contains a non-numeric value: {part!r}")
        ids.add(int(part))
    return frozenset(ids)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    anthropic_api_key: str
    allowed_user_ids: frozenset[int]
    timezone: str


def load_settings() -> Settings:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
    return Settings(
        bot_token=token,
        anthropic_api_key=api_key,
        allowed_user_ids=parse_user_ids(os.environ.get("ALLOWED_USER_IDS", "")),
        timezone=os.environ.get("TZ", "Europe/Stockholm"),
    )
