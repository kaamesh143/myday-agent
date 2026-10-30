# myday-agent

A self-hosted personal AI assistant on Telegram, built in the open as a
hands-on AI engineering learning project.

> **Status:** Week 1 baseline. The bot is a secure echo bot that replies only
> to allowed Telegram user IDs. Features arrive week by week, see the roadmap.

## What it will do

| Feature | Example |
|---|---|
| `/myday` at 07:00 and on request | Today's meetings, weather, and share picks from a labelled email |
| Ticket agent | "Send my flight tickets for next week" → PDF + QR from Gmail |
| Chat (text, later voice) | "Am I free Thursday afternoon?" |

## Quick start (local)

Prerequisites: Docker, a Telegram account.

1. In Telegram, open **@BotFather**, send `/newbot`, copy the token.
2. Configure:
   ```bash
   cp .env.example .env   # put the token in TELEGRAM_BOT_TOKEN
   ```
3. Run and find your user ID:
   ```bash
   docker compose up --build
   ```
   Message the bot. It won't reply; the log shows
   `Ignored message from unauthorized user id=...`.
4. Put that ID in `ALLOWED_USER_IDS` in `.env`, then:
   ```bash
   docker compose up --build -d
   ```
5. Send `/help`, then any text. It echoes back.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install        # gitleaks + ruff on every commit
ruff check . && pytest
```

## Security

- Replies only to Telegram IDs in `ALLOWED_USER_IDS`.
- Google access will be **read-only**.
- No personal data in this repo: tests use synthetic data only.
- Secrets live in `.env` (git-ignored). gitleaks runs locally and in CI.
- Found a vulnerability? See [SECURITY.md](SECURITY.md).

## Project plan and learning

- Full plan: [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md)
- Learning notes: [docs/learning/](docs/learning/)
- Decision records: [docs/adr/](docs/adr/)

## Disclaimer

Share summaries are information only, not financial advice. The bot has no
trading capability.

## License

[MIT](LICENSE)
