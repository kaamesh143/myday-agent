# Trip plan from Gmail

`/trip` and `/myday` show your upcoming travel, read from booking emails in Gmail.

## How it works

1. The bot searches Gmail (read-only) for booking emails from the last 6 months
   (subject words like booking, ticket, itinerary, confirmation, flight, hotel).
2. Claude reads those emails and returns a list of trip items as JSON:
   kind, title, date, time, arrival, booking reference, one line of details.
   Claude has no tools here, so text inside an email cannot make the bot do anything.
3. The list is saved in `data/trip_cache.json` for 6 hours, so `/myday` does not
   search Gmail and call Claude every time.
4. `/myday` adds a "Trip" section only when something starts in the next
   `TRIP_DAYS_AHEAD` days (default 30). If Gmail fails, `/myday` simply leaves it out.

## Just ask

Normal messages go to the agent loop with three tools: weather, `get_trip_plan` and
`find_booking_documents`. So "what is my plan on 20 Nov?" or "send my hotel booking" works
without a command. Claude picks the tool; our code runs it and sends any PDFs after the answer.

## Commands

| Command | What it does |
|---|---|
| `/trip` | The whole upcoming plan, grouped by day |
| `/trip refresh` | Search Gmail again now (after a new booking or a change) |
| `/trip <question>` | Ask about it, e.g. `/trip what time should I leave for the airport?` |
| `/ticket <words>` | Send the booking PDF(s) from Gmail to Telegram, e.g. `/ticket Scandic Rovaniemi`. Searches emails from the last year with a PDF attached; sends at most 3, newest first. If there is no PDF (Booking.com sends none), it replies with the booking details from `/trip` and Gmail links to the matching emails |

## Limits to know

- `/trip` reads only the email text, not PDF attachments (use `/ticket` to get the PDF itself). Most airline, train and hotel emails
  have the details in the text. If one is missing, forward the PDF to yourself as text or
  use `TRIP_GMAIL_QUERY` with a Gmail label you put on your bookings.
- Claude can misread an email. Always check times and terminals in the original booking.
- The email text is sent to the Anthropic API to extract the items. Cost is about
  one cent or less per refresh.

## Rollback

- Turn it off for `/myday`: nothing to do if no trip is coming; otherwise revert the PR.
- Remove Gmail access: <https://myaccount.google.com/permissions> → your app → Remove access,
  then run `python -m app.google_auth` again (it will ask for both scopes; to go back to
  calendar-only, revert this PR first).
- Delete `data/trip_cache.json` to remove the saved trip items.
