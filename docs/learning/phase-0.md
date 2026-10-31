# Phase 0: Claude API basics and first Telegram chat

Date: 2026-10-31. Written by Kaamesh, in his own words (spelling fixed only).

## What I learned

- Today we added the Anthropic library to the bot and tested that the Anthropic LLM
  (Haiku) gives a response locally.
- Then we added the cut-off flag and the cost details to the container logs.
- Then we tested by sending a chat to the Compass dev bot. Only my approved user ID
  has permission to use it.
- Claude connects in this session and gives a response. We found a bug in the logs:
  even though the user was approved, the log still showed a warning. That was fixed
  and deployed.

## What surprised me

(to add)

## Code I can now explain without help

(to add)

## Numbers (from my own tests and logs)

| Test | Input tokens | Output tokens | Cost (Haiku 5.5) | Cut off? |
|---|---|---|---|---|
| First call from code ("Say hello") | 12 | 13 | $0.000008 | No |
| Limit 20 tokens, morning routine | 25 | 20 | about $0.0000125 | Yes (`max_tokens`) |
| Limit 300 tokens, same question | 25 | 164 | about $0.0000845 | No (`end_turn`) |
| Telegram chat: token question | 88 | 62 | $0.000040 | No |
| Telegram chat: India capital | 82 | 83 | $0.000050 | No |
| Telegram chat: third question | 83 | 201 | $0.000109 | No |

## Open questions

(to add)
