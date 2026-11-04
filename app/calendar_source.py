"""Today's events from Google Calendar (read-only), formatted for /myday.

Several calendars can be combined, for example personal and office. A calendar can be
marked private: its events are then shown as "Busy", so no titles leave the calendar.
"""

import datetime
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google.auth.exceptions import GoogleAuthError, RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.google_token import CALENDAR_SCOPE, load_credentials

log = logging.getLogger("assistant")

SCOPES = [CALENDAR_SCOPE]
MAX_SHOWN = 10
MAX_TITLE = 80

NOT_CONNECTED = "Calendar is not connected yet (run the Google sign-in)."
SIGNED_OUT = "Calendar sign-in has expired. Please sign in again."
UNAVAILABLE = "Calendar is not available right now."


class CalendarError(Exception):
    """Calendar data could not be read or understood."""


@dataclass(frozen=True)
class Event:
    title: str
    start: datetime.datetime
    end: datetime.datetime
    all_day: bool


def parse_event(item: dict[str, Any], tz: ZoneInfo, *, private: bool) -> Event | None:
    """Turn one Google event into an Event. Returns None for events we do not show."""
    if item.get("status") == "cancelled":
        return None
    for attendee in item.get("attendees", []):
        if attendee.get("self") and attendee.get("responseStatus") == "declined":
            return None

    title = "Busy" if private else (item.get("summary") or "(no title)")
    title = title[:MAX_TITLE]
    start, end = item["start"], item["end"]
    if "date" in start:  # all-day event: Google gives dates, and the end date is exclusive
        first = datetime.date.fromisoformat(start["date"])
        last = datetime.date.fromisoformat(end["date"])
        return Event(
            title,
            datetime.datetime.combine(first, datetime.time.min, tz),
            datetime.datetime.combine(last, datetime.time.min, tz),
            all_day=True,
        )
    return Event(
        title,
        datetime.datetime.fromisoformat(start["dateTime"]).astimezone(tz),
        datetime.datetime.fromisoformat(end["dateTime"]).astimezone(tz),
        all_day=False,
    )


def fetch_events_today(
    service: Any,
    day: datetime.date,
    timezone: str,
    calendar_ids: Sequence[str],
    private_ids: frozenset[str] = frozenset(),
) -> list[Event]:
    """Read the events of one local day from every chosen calendar. All-day events come first."""
    tz = ZoneInfo(timezone)
    day_start = datetime.datetime.combine(day, datetime.time.min, tz)
    day_end = datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time.min, tz)
    events: list[Event] = []
    try:
        for calendar_id in calendar_ids:
            response = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=day_start.isoformat(),
                    timeMax=day_end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=50,
                )
                .execute()
            )
            for item in response.get("items", []):
                event = parse_event(item, tz, private=calendar_id in private_ids)
                if event is not None:
                    events.append(event)
    except (KeyError, ValueError, TypeError) as exc:
        raise CalendarError("Calendar data was not in the expected format.") from exc
    return sorted(events, key=lambda event: (not event.all_day, event.start))


def find_overlaps(events: list[Event]) -> dict[int, str]:
    """For each timed event, the title of the first other timed event it overlaps with.

    Events that only touch (one ends exactly when the next starts) do not overlap.
    """
    overlaps: dict[int, str] = {}
    for index, event in enumerate(events):
        if event.all_day:
            continue
        for other_index, other in enumerate(events):
            if other_index == index or other.all_day:
                continue
            if event.start < other.end and other.start < event.end:
                overlaps[index] = other.title
                break
    return overlaps


def format_events(events: list[Event], day: datetime.date) -> str:
    """One line per event, for example '09:00–10:00 Standup'."""
    if not events:
        return "No meetings today."
    overlaps = find_overlaps(events)
    lines = []
    for index, event in enumerate(events[:MAX_SHOWN]):
        if event.all_day:
            line = f"All day: {event.title}"
        else:
            if event.start.date() < day:
                label = f"until {event.end:%H:%M}"
            elif event.end.date() > day:
                label = f"from {event.start:%H:%M}"
            else:
                label = f"{event.start:%H:%M}–{event.end:%H:%M}"
            line = f"{label} {event.title}"
            if index in overlaps:
                line += f" (overlaps with {overlaps[index]})"
        lines.append(line)
    if len(events) > MAX_SHOWN:
        lines.append(f"+{len(events) - MAX_SHOWN} more")
    return "\n".join(lines)


def build_service(token_path: Path) -> Any:
    """Open the Calendar API with the saved token, refreshing it when it has expired."""
    credentials = load_credentials(token_path)
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def get_calendar_text(
    token_path: Path,
    timezone: str,
    calendar_ids: Sequence[str],
    private_ids: frozenset[str] = frozenset(),
    *,
    service_factory: Callable[[Path], Any] = build_service,
    now: datetime.datetime | None = None,
) -> str:
    """Today's events as text for /myday. Calendar problems become a short message, not an error."""
    if not token_path.exists():
        return NOT_CONNECTED
    tz = ZoneInfo(timezone)
    day = (now or datetime.datetime.now(tz)).astimezone(tz).date()
    try:
        service = service_factory(token_path)
        events = fetch_events_today(service, day, timezone, calendar_ids, private_ids)
    except RefreshError:
        log.warning("Calendar sign-in has expired")
        return SIGNED_OUT
    except (CalendarError, HttpError, GoogleAuthError, OSError) as exc:
        # Log the error type only, never event content.
        log.warning("Calendar could not be read: %s", type(exc).__name__)
        return UNAVAILABLE
    return format_events(events, day)
