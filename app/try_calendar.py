"""Manual check: print today's calendar exactly as /myday would show it.

Run: docker compose run --rm bot python -m app.try_calendar
"""

from app.calendar_source import get_calendar_text
from app.config import load_settings


def main() -> None:
    settings = load_settings()
    print(
        get_calendar_text(
            settings.google_token_path,
            settings.timezone,
            settings.calendar_ids,
            settings.private_calendar_ids,
        )
    )


if __name__ == "__main__":
    main()
