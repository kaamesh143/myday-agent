# Instructions for AI coding agents

This repo is a **learning project**. The owner is learning Python and AI
engineering, so how you help matters as much as what you produce.

## Working rules

1. Explain every new function in plain English in your reply: what it does,
   why, and one thing that could go wrong.
2. Prefer small, readable code over clever code. Add type hints.
3. Every change needs a test in `tests/`.
4. Run `ruff check . && pytest -q` before saying a change is done.
5. When the owner asks for a "no-AI exercise", give hints, not the solution.

## Hard rules

- Never commit secrets, tokens, real emails, tickets or any personal data.
  Test data must be synthetic.
- Google access is read-only. Do not add send/delete/modify scopes.
- The bot must only respond to `ALLOWED_USER_IDS`. Never weaken this.
- Never log full message contents, tokens or email bodies.

## Layout

- `app/`: bot code (`bot.py` entry point, `config.py` settings)
- `tests/`: pytest tests
- `docs/PROJECT_PLAN.md`: the plan; `docs/adr/`: decisions; `docs/learning/`: notes
