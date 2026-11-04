"""Manual check: search Gmail for bookings and print the trip plan as /trip would show it.

Run: docker compose run --rm bot python -m app.try_trip
It always searches Gmail again (like /trip refresh) and costs one small Claude request.
"""

import anthropic

from app.config import load_settings
from app.gmail_source import DEFAULT_QUERY
from app.trip import TripConfig, trip_reply


def main() -> None:
    settings = load_settings()
    config = TripConfig(
        token_path=settings.google_token_path,
        cache_path=settings.trip_cache_path,
        timezone=settings.timezone,
        query=settings.trip_gmail_query or DEFAULT_QUERY,
        days_ahead=settings.trip_days_ahead,
    )
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    print(trip_reply(config, client, "refresh"))


if __name__ == "__main__":
    main()
