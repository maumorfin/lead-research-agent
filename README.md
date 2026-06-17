# Pro Cycling Intelligence Agent

A conversational AI agent that answers natural language questions about professional cycling — standings, race results, rider profiles, stage data, and live race notifications — delivered via a Telegram bot or CLI.

Built with **LangGraph** on a **Plan & Execute** pattern. Supports **Claude Sonnet 4**, **Claude Haiku 4.5**, and **Llama 3.3 70b on Groq** — switchable live inside Telegram with a single tap. Conversations are persistent: follow-up questions work naturally, the agent remembers what you care about across sessions, and it watches live races for you in the background.

> **Current branch:** `feature/proactive-agent` — adds a background race watcher that sends Telegram notifications when something important happens during a live stage: attacks, crashes, breakaways, stage wins.

---

## What It Does

**Reactive (question-answer):** Ask anything about pro cycling and the agent will:
1. **Resolve** — rewrites pronouns and vague references into self-contained questions ("he" → "Tadej Pogačar")
2. **Plan** — the active LLM decides which tools to use and in what order
3. **Execute** — fetches data using the right tool (no AI in this step)
4. **Synthesize** — responds like a knowledgeable friend who remembers what was just discussed
5. **Remember** — conversation history persists within a session; your interests accumulate across sessions

**Proactive (live notifications):** Subscribe to a race with `/watch` and the bot will:
1. **Poll** — checks the race page every 60 seconds for content changes
2. **Filter (rule engine)** — free keyword filter discards ~90% of routine updates instantly
3. **Filter (LLM judge)** — Groq decides if the remaining 10% is worth a notification
4. **Notify** — sends a Telegram message only for meaningful events (attacks, crashes, gaps, stage wins)

---

## Architecture

### Reactive pipeline (one question → one answer)

```
User question
      │
      ▼
┌─────────────┐
│  SUMMARIZER │  Compresses history when it exceeds 20 messages
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   RESOLVER  │  Rewrites ambiguous questions using the last 6 messages
│             │  "What did he win?" → "What did Tadej Pogačar win in 2026?"
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   PLANNER   │  Active model generates a 2–5 step research plan
│             │  ← injects user profile (riders you follow, language, past topics)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   EXECUTOR  │  Runs each step — PCS, Tavily, Firecrawl, static scrape (no AI)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ SYNTHESIZER │  Active model produces a conversational answer
│             │  ← receives recent conversation history for natural tone
└──────┬──────┘
       │
       ▼
  CyclingAnswer  (stored in checkpoints.db for next follow-up)
```

### Proactive watcher (runs in background, sends notifications)

```
Every 60 seconds:
      │
      ▼
 Calendar agent  ←── PCS homepage scrape (primary, free, no LLM) (once per 20h)
      │                  └── Tavily+Groq fallback if homepage blocked
      │                  Discovers active races automatically — no manual updates needed
      │
      ▼
  Race poller  ←── httpx GET of PCS live race page
      │               If 403 → persistent Playwright browser (launched once, reused)
      │               MD5 hash comparison against last snapshot
      │               Extracts diff: only new sentences since last poll
      │
      ├─ no change → sleep, try again in 60s
      │
      ▼
 Rule engine  ←── keyword filter (~0ms, free)
      │               HIGH: attack, crash, abandon, breakaway, solo, gap, bridge
      │               MEDIUM: summit, sprint, jersey, GC, winner
      │               Blocks ~90% of diffs before calling any LLM
      │
      ├─ blocked → sleep
      │
      ▼
 Groq judge   ←── Groq Llama 3.3 70b (~500ms, ~$0.0001 per call)
      │               Reads diff + race context + user profile
      │               Decides: notify or not, and writes the message
      │
      ├─ skip → sleep
      │
      ▼
 Dispatcher  ←── sends Telegram message to all subscribed users
```

---

## Memory Layers

| Layer | What it stores | File |
|---|---|---|
| **In-thread** | Full conversation history for the current session | `data/checkpoints.db` |
| **Session** | Thread ID + last-active timestamp per chat | `data/sessions.db` |
| **Long-term** | Riders, races, language, session summaries per user | `data/user_profiles.db` |
| **Subscriptions** | Which users are watching which race + stage | `data/subscriptions.db` |
| **Race calendar** | Active and upcoming races, auto-refreshed daily | `data/races.db` |

All five databases are created automatically in `data/` on first run and are gitignored. Each Telegram user's data is isolated by `chat_id`.

### Session lifecycle

A session expires after **2 hours of inactivity**. On the next message:
1. Groq extracts key facts from the old thread (riders, races, language, summary)
2. Facts are merged into the user's long-term profile (never overwritten — always accumulated)
3. A fresh thread starts, with the profile pre-loaded into the planner's system prompt

---

## Live Race Watcher

### Subscribing

```
/watch      → shows inline menu of live and upcoming races
              tap a race to subscribe (tap again to unsubscribe)

/watching   → lists your active subscriptions

/unwatch    → removes all your subscriptions
```

### What triggers a notification

The two-gate pipeline filters aggressively to avoid noise:

| Gate | Signals that pass | Cost |
|---|---|---|
| **Rule engine** (Gate 1) | attack, crash, abandon, breakaway, solo, gap is, time gap, bridge, dropped, caught, counter-attack, sprint (+ medium keywords with rider match) | free |
| **Groq judge** (Gate 2) | LLM confirms the event is meaningful for this specific user's profile | ~$0.0001 |
| **Blocked** | routine updates, stats, weather, km done, virtual GC with no changes | free |

**Notification format:**
```
📡 Giro d'Italia — Stage 12

Pogačar has attacked on the final climb. Vingegaard is 15 seconds behind
and struggling. The gap is growing fast — this could decide the stage.
```

### Race calendar

The watcher discovers active races automatically using a daily refresh cycle:
1. **PCS homepage scrape** (primary) — parses the `hp3-livestats` section on `procyclingstats.com/`. Slugs and stages come directly from PCS hrefs — no LLM, no API cost, 0 errors from hallucination.
2. **Tavily + Groq fallback** — used only if the homepage is unreachable. 1 Tavily call + 1 Groq call, then PCS validation confirms each result.
3. **SQLite store** — writes valid races, skips bad data, never deletes existing races.

If a refresh returns zero valid races, the existing data is preserved and the refresh timestamp is not updated (so it retries next cycle).

---

## Models

Switch models live in Telegram with `/model`. Each chat remembers its own choice.

| Key | Model | Provider | Speed | Notes |
|---|---|---|---|---|
| `sonnet` | `claude-sonnet-4-6` | Anthropic | ~3–5s | Default — best quality |
| `haiku` | `claude-haiku-4-5-20251001` | Anthropic | ~2–3s | Faster and cheaper |
| `groq` | `llama-3.3-70b-versatile` | Groq | ~1–2s | Free tier, very fast |

The **judge** and **handoff extractor** always use Groq regardless of the user's model choice — they need to be fast and cheap.

---

## Tools

| Tool | When used | How |
|---|---|---|
| `pcs_ranking` | WorldTour standings | Tavily web search |
| `pcs_rider` | Rider profiles and career stats | Tavily web search |
| `pcs_race` | Race overviews and GC results | Tavily web search |
| `pcs_stage` | Individual stage results | Tavily web search |
| `pcs_startlist` | Who is riding a race | Tavily web search |
| `pcs_rider_results` | Rider's season results | Tavily web search |
| `search` | News, recent updates, general info | Tavily web search |
| `scrape` | Static HTML pages | httpx + BeautifulSoup |
| `firecrawl` | Live race data (JS-rendered pages) | Playwright + Firecrawl fallback |

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message with all available commands |
| `/help` | Example questions by category |
| `/status` | Current WorldTour top 5 |
| `/model` | Switch AI model with inline buttons |
| `/watch` | Subscribe to live race notifications |
| `/watching` | List your active subscriptions |
| `/unwatch` | Remove all your subscriptions |
| Any text | Runs the full agent pipeline; follow-ups remember context |

---

## How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Set up API keys
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, GROQ_API_KEY, TAVILY_API_KEY,
#          FIRECRAWL_API_KEY, TELEGRAM_BOT_TOKEN

# 3. Test the CLI (no Telegram needed)
python main.py "Who leads the WorldTour?"
python main.py "And what about the team standings?"   # follow-up — pronouns resolved

# 4. Run the Telegram bot (includes background watcher)
python bot.py
```

The bot starts a background asyncio task that:
- Runs a calendar refresh on startup
- Polls subscribed races every 60 seconds
- Refreshes the race calendar automatically every 20 hours

---

## Tests

```bash
# Rule engine — 31 unit tests, no API keys needed, ~1 second
python tests/test_rules.py

# Groq judge — 9 tests with real API calls (~5 calls to Groq)
python tests/test_judge.py

# Live poller — polls PCS for 3 minutes at 10s interval (interactive)
python tests/test_poller.py
```

---

## Example Questions

| Category | Question |
|---|---|
| Standings | Who is leading the UCI WorldTour? |
| Standings | Show me the top 10 WorldTour teams |
| Riders | What are Tadej Pogačar's career stats? |
| Riders | Show me Remco Evenepoel's 2026 results |
| Races | Who won the 2026 Giro d'Italia? |
| Stages | What happened in stage 10 of the Tour de France 2026? |
| Startlists | Who is riding the Vuelta 2026? |
| News | What is the latest news about Jonas Vingegaard? |
| Live | What is happening in the race right now? |
| Follow-up | And what is the time gap to second place? |
| Follow-up | Tell me more about the stage winner |
| Pronoun | What did he win this spring? *(resolves to last rider discussed)* |

---

## Project Structure

```
.
├── agent/
│   ├── graph.py          # LangGraph StateGraph — 5 nodes wired together
│   ├── executor.py       # Runs the planner's steps, calls tools
│   ├── llm_client.py     # Unified call_llm() for Anthropic + Groq
│   ├── planner.py        # (legacy — planning is now in graph.py)
│   └── synthesizer.py    # (legacy — synthesis is now in graph.py)
├── memory/
│   ├── session_manager.py  # 2-hour session tracking in sessions.db
│   ├── user_store.py       # Long-term profile accumulation in user_profiles.db
│   └── handoff.py          # Groq-powered fact extraction on session expiry
├── watcher/
│   ├── poller.py           # httpx poller with MD5 hash diff detection
│   ├── rules.py            # Keyword rule engine — Gate 1 (free)
│   ├── judge.py            # Groq LLM judge — Gate 2 (~$0.0001/call)
│   ├── dispatcher.py       # Glues poller → rules → judge → Telegram
│   ├── subscription_store.py  # SQLite — who watches what
│   ├── race_store.py       # SQLite — dynamic race calendar
│   └── calendar_agent.py  # Tavily+Groq race discovery, runs once/day
├── tools/
│   ├── cycling_pcs.py    # PCS-specific tool wrappers
│   ├── web_search.py     # Tavily search
│   ├── web_scraper.py    # httpx + BeautifulSoup static scraping
│   └── live_scraper.py   # Playwright + Firecrawl for JS-rendered pages
├── models/
│   ├── plan.py           # ResearchPlan dataclass
│   └── answer.py         # CyclingAnswer dataclass
├── tests/
│   ├── test_rules.py     # 31 rule engine unit tests
│   ├── test_judge.py     # 9 Groq judge integration tests
│   └── test_poller.py    # Live poller manual test (3 min, 10s interval)
├── bot.py                # Telegram bot + background watcher loop
├── main.py               # CLI entry point
├── config.py             # Model registry + per-chat model selection
└── playground.ipynb      # Interactive testing without Telegram
```

---

## Known Limitations

- **Model choice is in-memory.** Restarting `bot.py` resets model selection to Claude Sonnet, but conversation history, user profiles, and subscriptions survive (SQLite).
- **PCS blocks plain httpx with 403 on live pages.** The first 403 launches a persistent Chromium browser (one instance, reused for the rest of the session). Subsequent polls for that race skip httpx entirely and go straight to the browser tab — no re-launch per poll.
- **Groq tool-call reliability.** Llama 3.3 occasionally produces malformed tool call responses (CDATA strings, missing closing tags, array-wrapped JSON). The agent recovers automatically via regex fallback in `llm_client.py`.
- **Firecrawl is for live races only.** 500 free pages/month. Only called when a race is actively happening.
- **Playwright requires Chromium.** Run `playwright install chromium` once before using live scraping.
- **Calendar refresh quality depends on Tavily results.** Stage numbers found via web search may lag behind real race progress by a few hours.

---

## Tech Stack

| | |
|---|---|
| [LangGraph](https://langchain-ai.github.io/langgraph/) | StateGraph orchestration + SqliteSaver checkpointing |
| [Anthropic SDK](https://anthropic.com) | Claude Sonnet 4 and Haiku 4.5 |
| [Groq](https://console.groq.com) | Llama 3.3 70b via OpenAI-compatible SDK |
| [Tavily](https://tavily.com) | Web search + calendar discovery |
| [Firecrawl](https://firecrawl.dev) | Headless browser for live race pages |
| [Playwright](https://playwright.dev) | Chromium scraping for real-time race data |
| [python-telegram-bot](https://python-telegram-bot.org/) | Async Telegram bot framework |
| [httpx](https://www.python-httpx.org/) | Async HTTP client for polling |
| [Pydantic v2](https://docs.pydantic.dev) | Data schemas and validation |
| [Rich](https://github.com/Textualize/rich) | Terminal UI for CLI mode |

---

## Branch History

| Branch | What it introduced |
|---|---|
| [`cycling-agent`](../../tree/cycling-agent) | Original agent — Claude only, no memory |
| [`groq-migration`](../../tree/groq-migration) | Added Groq Llama 3.3 70b as an alternative |
| [`feature/model-fusion`](../../tree/feature/model-fusion) | Multi-model support — Claude + Groq switchable via `/model` |
| [`feature/langgraph-memory`](../../tree/feature/langgraph-memory) | LangGraph pipeline, persistent memory, pronoun resolution, user profiles |
| [`feature/proactive-agent`](../../tree/feature/proactive-agent) | **This branch** — background race watcher, live notifications, self-maintaining race calendar |

---

## License

MIT
