# Security policy

## Reporting a vulnerability

Please **do not** open a public issue. Use GitHub's
[private vulnerability reporting](../../security/advisories/new) for this repo.
I aim to respond within 7 days.

## Design principles

- Allowlist: the bot answers only configured Telegram user IDs.
- Least privilege: Google scopes are read-only.
- The agent can only reply in the owner's own chat; it has no tool to email
  or message anyone else (prompt-injection containment).
- Secrets only in `.env` / secret stores; gitleaks in pre-commit and CI.
- No personal data in the repository; tests and evals use synthetic data.
