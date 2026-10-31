# myday-agent: project plan

Single source of truth for scope, learning goals, architecture and roadmap.
Last updated: 2026-10-30.

## 1. Business context

**Problem:** schedule, share recommendations and travel tickets are spread
across Google Calendar and Gmail. One Telegram chat should bring them together.

**User:** the owner only (one allowed Telegram ID). Google data: owner's
account, read-only.

| ID | Requirement | Example |
|---|---|---|
| R1 | `/myday` at **07:00 daily** (Europe/Stockholm) **and on request**: meetings, weather, share picks | `/myday` → "3 meetings, 8°C rain, Buy: X, Sell: Y" |
| R2 | Ticket agent: plain-language request → search Gmail → send PDF tickets and QR codes | "Send my flight tickets for next week" |
| R3 | Chat by text; voice notes from week 16 | "Am I free Thursday afternoon?" |
| R4 | High security | Allowlist, read-only scopes, no data leaks |
| R5 | Open source (MIT) and generic | Personal settings in config, not code |

**Decisions**

| Topic | Decision |
|---|---|
| Share email | Found by Gmail label `Assistant/Shares` |
| Future sources | Pluggable: each source is a config entry (label + prompt + schema) |
| Weather | Malmö by default; trip city when calendar/bookings show travel (Open-Meteo) |
| Missed 07:00 run | Sent on restart, marked "(late)" |
| Weekends | Brief says "No share update today" when no email |

**Out of scope:** WhatsApp, Jarvis (separate project), sending/deleting
email, trading actions.

**Known limitation:** QR codes that exist only in an airline app or behind a
website login cannot be fetched; the bot sends booking details and the link.

**Success criteria**

| Measure | Target |
|---|---|
| `/myday` reply time | < 15 s |
| Ticket agent finds the right ticket | ≥ 9/10 eval cases |
| Personal data or secrets in repo | 0 (gitleaks, synthetic data) |
| Running cost | < $2/month |

## 2. Learning context

**Learner:** Kaamesh. Strong in concepts (agents, MCP, skills), DevOps and
analysis; has shipped production apps with AI-assisted coding. Gap: reading
and writing Python unaided.

**Goal:** understand every line; build, measure (evals) and secure AI systems.

**Time:** weekdays 1 h, Saturday 2 h, Sunday 2 h (~9 h/week).

| Weekday (1 h) | Saturday (2 h) | Sunday (2 h) |
|---|---|---|
| 10 min concept · 30 min build with Claude · 15 min explain-back / no-AI task · 5 min notes | Bigger build + tests | Quiz, learning note, "Know" reading, plan next week |

**Python checkpoints (no AI):** week 4 explain any file; week 12 write a tool
+ test unaided; week 16 fix a deliberately planted bug.

## 3. Implementation context

```
Telegram ◄─polling─► Orchestrator (harness)
                      ├─ Claude Haiku 5.5 / Sonnet 5.5 (provider layer: Ollama for experiments)
                      ├─ Tools: calendar · weather · share_email · search_email · send_ticket
                      │         (native, MCP, UTCP variants)
                      ├─ A2A sub-agents (feature flag): travel · market-brief
                      ├─ RAG: local embeddings + sqlite-vec
                      ├─ Hooks: allowlist · injection checks · output checks · PII masking
                      └─ SQLite · encrypted Google token · /data/docs
```

| Area | Choice |
|---|---|
| Chat | Telegram, `python-telegram-bot` (polling, no open ports) |
| LLM | Claude Haiku 5.5 (main), Sonnet 5.5 (hard tasks, eval judge), Ollama on M4 (experiments) |
| Embeddings | `nomic-embed-text` / `bge-small` (local) |
| Voice | mlx-whisper (Mac), faster-whisper (server) |
| Google | Calendar + Gmail APIs, read-only |
| Frameworks | Hand-written agent first, then LangGraph; MCP, UTCP, A2A |
| Evals / tracing | pytest + LLM-as-judge, Ragas, promptfoo/DeepEval; Langfuse, OpenTelemetry GenAI |
| Runtime | Docker Compose; M4 laptop (dev) → Oracle Always Free ARM VM (prod) |

### 3A. Agent harness

Context builder (system prompt, history, memory, RAG, date) → agent loop with
stop conditions → tool registry → pre/post-tool hooks → budgets (max steps,
tokens, cost, time) → retries/timeouts/fallbacks → state (SQLite) → tracing.

Second harness: **eval harness**: dataset → runner → graders (exact, rules,
LLM-as-judge) → report (score, cost, latency) → compare with baseline.

### 3B. AI deployment pipeline

```
commit → pre-commit (gitleaks, ruff) → CI (tests, mypy, pip-audit, CodeQL)
→ AI quality gate (PR: small eval; nightly/release: full eval + red-team)
→ build arm64 image (Trivy, SBOM) → staging (test bot, smoke tests) → prod → monitor
```

- Gate fails on: score drop > 5 %, cost/latency up > 20 %, any safety test failing.
- Prompts in `prompts/*.md`, model config in `config/models.yaml`: versioned and eval-gated.
- Pull-based deploy: the VM pulls signed images; GitHub never logs in to the server.
- Rollback: previous image tag (~1 min); `git revert` for prompts; DB backup before migrations.
- Graceful degradation: Claude down → calendar + weather still delivered.
- Feedback: 👍/👎 buttons → new synthetic eval cases.

| Env | Where | Bot | Data |
|---|---|---|---|
| Dev | M4 laptop | test bot | owner's (local) |
| CI | GitHub runners | mocked | synthetic |
| Staging | Oracle VM | test bot | owner's |
| Prod | Oracle VM | real bot | owner's |

### 3C. Protocols

| Protocol | Connects | Use here |
|---|---|---|
| MCP | agent ↔ tools | Tools as an MCP server (week 5) |
| UTCP | agent ↔ tools, no wrapper | Weather tool via UTCP manual; compare with MCP/native (week 6) |
| A2A | agent ↔ agent | Orchestrator + travel + market-brief agents behind a flag (week 13) |
| AG-UI | agent ↔ UI | Know only |

### 3D. Other topics

| Topic | Level | Week |
|---|---|---|
| AGENTS.md | Build | 1 |
| Prompt caching | Build | 2 |
| Agent Skills | Build | 4 |
| Remote MCP + OAuth | Explore | 5 |
| Long-term memory | Build | 7 |
| Ragas | Build | 10 |
| promptfoo / DeepEval | Explore | 12 |
| Guardrail models, NeMo Guardrails | Explore | 14 |
| OpenTelemetry GenAI | Build | 15 |
| Computer-use agents, AG-UI, governance | Know | Sundays |
| Fine-tuning (LoRA, MLX) | Explore | after v1.0 |

### Security controls

1. Telegram ID allowlist.
2. Read-only Google scopes; token encrypted at rest.
3. Agent can only reply in the owner's chat.
4. Prompt-injection and A2A attack tests in the quality gate.
5. gitleaks (pre-commit + CI), GitHub secret scanning, Dependabot, CodeQL.
6. Synthetic test data only; audit log; no message bodies in logs.
7. Server: no open ports, SSH keys only. Telegram bot chats are not E2E encrypted.

## 4. Roadmap

| Week | Dates | Main work | Additions | Output |
|---|---|---|---|---|
| 1 | 2–8 Nov | `/myday` v1: calendar + weather; harness skeleton | AGENTS.md, pre-commit, CI | Working `/myday`, ADR-0001, `phase-0.md` |
| 2 | 9–15 Nov | Share email → `/myday`; structured output; 07:00 schedule | Prompt files, prompt caching, pluggable sources | `/myday` v2 + schema tests |
| 3–4 | 16–29 Nov | Ticket agent (PDF + QR); full agent loop | Budgets, hooks, Agent Skill | Agent + `phase-2.md` |
| 5 | 30 Nov–6 Dec | LangGraph + MCP | Remote MCP + OAuth | Harness comparison |
| 6 | 7–13 Dec | Tool protocols: native vs MCP vs UTCP | — | ADR "MCP vs UTCP" |
| 7 | 14–20 Dec | RAG 1: embeddings, vector DB | Memory | Search over email history |
| 8–9 | 21 Dec–3 Jan | Buffer / holidays | — | — |
| 10 | 4–10 Jan | RAG 2: hybrid search, reranking | Ragas | Retrieval scores |
| 11–12 | 11–24 Jan | Eval harness + AI quality gate | promptfoo / DeepEval; Claude vs Ollama | Evals in CI + report |
| 13 | 25–31 Jan | Multi-agent with A2A | — | Single vs multi comparison |
| 14 | 1–7 Feb | Safeguards + red-team | Guardrail models | Security report |
| 15 | 8–14 Feb | Deploy pipeline → Oracle | OpenTelemetry GenAI | Running 24/7, runbook |
| 16 | 15–21 Feb | Voice notes, QR, feedback loop | — | Demo video |
| 17 | 22–28 Feb | v1.0 release | Stretch: MLX fine-tuning | Release, blog post, retrospective |

## 4A. Learning tracks

Each track is taught through a feature of the bot.

| Track | Concepts | Where it is used |
|---|---|---|
| A. Python for AI | Functions, types, classes, async, pytest | Every week |
| B. LLM basics | Tokens, cost, models, prompts, structured output, caching | `/myday` summary (Wk 1-2) |
| C. Agents | Agent loop, tool use, budgets, hooks, Agent Skills | Ticket agent (Wk 3-5) |
| D. Frameworks and protocols | LangGraph, MCP, UTCP, A2A | Same agent rebuilt and compared (Wk 5-6, 13) |
| E. Retrieval | Embeddings, vector DB, RAG, reranking, memory | Questions about past emails (Wk 7-10) |
| F. Evals | Datasets, graders, LLM-as-judge, Ragas, promptfoo, CI gate | Quality gate (Wk 10-12) |
| G. Safety | Prompt injection, guardrails, OWASP LLM Top 10, red-team | Attack tests (Wk 14) |
| H. LLMOps and deployment | Tracing, cost tracking, OpenTelemetry, CI/CD, rollback | Oracle VM (Wk 15) |
| I. Multimodal and local models | Whisper, QR from PDF, Ollama comparison | Voice and Claude-vs-local evals (Wk 11, 16) |

## 4B. Priority levels

If the schedule slips, cut from the bottom, not the top.

| Level | Items | If behind |
|---|---|---|
| Must | Python, LLM basics, agent loop, RAG, evals, safety, deployment | Never cut |
| Build | LangGraph, MCP, UTCP, Ragas, Langfuse, prompt caching | Shorten |
| Explore | A2A multi-agent, NeMo Guardrails, promptfoo comparison, MLX fine-tuning | Drop first |
| Know | AG-UI, computer-use agents, governance (Sunday reading only) | Reading list |

## 4C. Checkpoints and proof of learning

- Each phase: one learning note in `docs/learning/`, written in the owner's own words.
- Python checkpoints, without AI: week 4 (explain any file), week 12 (write a tool and its test alone), week 16 (find and fix a planted bug).
- AI checkpoints: eval scores that improve across versions, and a cost figure per request.
- Final portfolio: public repo, ADRs, eval report, security report, blog post, demo video.

## 4D. Learning risks

| Risk | Mitigation |
|---|---|
| About 9 hours a week is tight for 17 weeks | Priority levels above; holiday buffer in weeks 8-9 |
| Using AI to write everything | Explain-back and no-AI tasks each week |
| Framework before fundamentals | Hand-written agent first (weeks 3-4) |
| Cost surprises | $5 spend limit; token and cost logging from Week 1 |

Pacing decision (31 Oct 2026): keep the 17-week timeline. Cut Explore items first if behind.

## 5. Open items

| Item | Needed by |
|---|---|
| Anthropic API key with monthly spend limit | Week 1 Tue |
| Google Cloud project + OAuth (read-only) | Week 1 Thu |
| Gmail label `Assistant/Shares` + filter | Week 2 |
