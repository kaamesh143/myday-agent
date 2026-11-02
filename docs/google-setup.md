# Google Calendar setup (read-only)

One-time setup so the bot can read your calendar. It never gets permission to change anything.
Takes about 20 minutes. The Google console menus change from time to time, so follow the
intent of each step if a label differs.

## 1. Create a Google Cloud project

1. Open the Google Cloud console and create a project, for example `myday-agent`.
2. Open **APIs and services → Library**, search for **Google Calendar API**, and click **Enable**.

## 2. Configure the OAuth consent screen

1. Open **APIs and services → OAuth consent screen** (also called Google Auth platform).
2. User type: **External**. Fill in an app name and your own email.
3. Scopes: add only `.../auth/calendar.readonly`. Do not add any other scope.
4. Add your own Google account as a **test user**.
5. **Publish the app** (set the publishing status to **In production**).
   If it stays in "Testing", Google expires your login every 7 days and the bot stops reading
   your calendar. For personal use, the "Google has not verified this app" warning is expected:
   you are the only user. Choose Advanced, then continue.

## 3. Create the OAuth client

1. Open **Credentials → Create credentials → OAuth client ID**.
2. Application type: **Desktop app**. Name it `myday-agent-desktop`.
3. Download the JSON file and save it in the project as `data/credentials.json`.
   The `data/` folder is ignored by git. Never commit, paste or share this file.

## 4. Sign in once, on your own computer

```bash
python -m app.google_auth
```

Your browser opens. Sign in, read what is requested (it should say "See and download any
calendar you can access"), and approve. The script saves `data/token.json`. This file is a secret:
only your user can read it, and it must never go into git.

## 5. Check it

```bash
docker compose run --rm bot python -m app.try_calendar
```

You should see today's events. Then send `/myday` to the bot.

## Adding your office calendar

The bot reads Google calendars only. It never connects to your employer's systems directly.
Get the office events into a Google calendar you can read, then list that calendar in `.env`.

| Your office uses | Way to get it into Google Calendar |
|---|---|
| Google Workspace | Ask the owner or IT to share the office calendar with your personal account. "See only free/busy" is enough for `/myday` |
| Outlook / Microsoft 365 | Publish the calendar as an ICS link and add it in Google Calendar under **Other calendars → From URL**. Google refreshes these slowly (up to about a day), so recent changes can be missing |
| Not sure | Check how you open the office calendar, then ask IT |

**Check your company policy first.** Publishing or sharing a work calendar outside the
company can break security rules. If in doubt, ask IT.

Then find the calendar's ID (Google Calendar → Settings → the calendar → **Integrate calendar**)
and set, in `.env`:

```
CALENDAR_IDS=primary,the-office-calendar-id
CALENDAR_PRIVATE_IDS=the-office-calendar-id
```

Calendars listed in `CALENDAR_PRIVATE_IDS` appear as **Busy**, with no titles, so confidential
meeting names never reach Telegram. Overlaps between your personal and office events are flagged.

Note: calendars shared as "free/busy only" may not be readable event by event through the
Google API. If the office calendar shows nothing, tell the maintainer so the code can switch to
Google's dedicated free/busy request.
