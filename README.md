# Pro Cycling Intelligence Agent

A conversational AI agent that answers natural language questions about professional cycling — standings, race results, rider profiles, stage data, and live race updates — delivered via a Telegram bot or CLI.

Built with **LangGraph** on a **Plan & Execute** pattern. Supports **Claude Sonnet 4**, **Claude Haiku 4.5**, and **Llama 3.3 70b on Groq** — switchable live inside Telegram with a single tap. Conversations are persistent: follow-up questions work naturally, and the agent remembers what you care about across sessions.

> **Branch:** `feature/langgraph-memory` — LangGraph refactor with in-thread memory, summarization, pronoun resolution, 2-hour session management, and long-term user profiles.

---

## What It Does

Ask it anything about pro cycling and it will:
1. **Resolve** — rewrites pronouns and vague references into self-contained questions ("he" → "Tadej Pogačar")
2. **Plan** — the active LLM decides which tools to use and in what order
3. **Execute** — fetches data using the right tool (no AI in this step)
4. **Synthesize** — responds like a knowledgeable friend who remembers what was just discussed
5. **Remember** — conversation history persists within a session; your interests are saved across sessions

---

## Architecture

```
Question
    │
    ▼
┌──────────────┐
│  SUMMARIZER  │  Compresses history when it exceeds 20 messages (keeps cost flat)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   RESOLVER   │  Rewrites ambiguous questions using the last 6 messages
│              │  "What did he win?" → "What did Tadej Pogačar win in 2026?"
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   PLANNER    │  Active model generates a 2–5 step research plan
│              │  ← injects user profile (riders you follow, language, past topics)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   EXECUTOR   │  Runs each step — Tavily, Firecrawl/Playwright, static scrape (no AI)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  SYNTHESIZER │  Active model produces a conversational CyclingAnswer
│              │  ← receives recent conversation history for natural tone
│              │  ← appends Q&A to conversation history
└──────┬───────┘
       │
       ▼
 CyclingAnswer ✓  (stored in checkpoints.db for next follow-up)
```

### Memory layers

| Layer | What it stores | Where |
|---|---|---|
| **In-thread** | Full conversation history for the current session | `data/checkpoints.db` (LangGraph SqliteSaver) |
| **Session** | Thread ID + last-active timestamp per chat | `data/sessions.db` |
| **Long-term** | Riders, races, language, session summaries per user | `data/user_profiles.db` |

A session expires after **2 hours of inactivity**. On the next message, the agent extracts key facts from the old thread and saves them to the user's long-term profile before starting a fresh thread.

All three databases are created automatically in `data/` on first run. They are gitignored and isolated by `chat_id` — each Telegram user's data is completely separate.

---

## Models

Switch models live in Telegram with the **⚙️ Change Model** button or `/model`. Each chat remembers its own choice independently.

| Key | Model | Provider | Notes |
|---|---|---|---|
| `sonnet` | `claude-sonnet-4-6` | Anthropic | Default — best quality and reliability |
| `haiku` | `claude-haiku-4-5-20251001` | Anthropic | Faster and cheaper |
| `groq` | `llama-3.3-70b-versatile` | Groq | Free tier, very fast |

---

## Tools

| Tool | When it's used | How it works |
|---|---|---|
| `pcs_ranking` | WorldTour standings | Tavily web search |
| `pcs_rider` | Rider profiles and career stats | Tavily web search |
| `pcs_race` | Race overviews and GC results | Tavily web search |
| `pcs_stage` | Individual stage results | Tavily web search |
| `pcs_startlist` | Who is riding a race | Tavily web search |
| `pcs_rider_results` | Rider's season results | Tavily web search |
| `search` | News, recent updates, general info | Tavily web search |
| `scrape` | Static HTML pages | httpx + BeautifulSoup |
| `firecrawl` | Live race data happening right now | Playwright (Chromium) + Firecrawl fallback |

---

## How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Set up API keys — copy and fill in all five
cp .env.example .env
# ANTHROPIC_API_KEY, GROQ_API_KEY, TAVILY_API_KEY, FIRECRAWL_API_KEY, TELEGRAM_BOT_TOKEN

# 3. Test with the CLI (no Telegram needed)
python main.py "Who leads the WorldTour?"

# 4. Ask a follow-up in the same session (same chat_id=0)
python main.py "And what about the team standings?"

# 5. Run the Telegram bot
python bot.py
```

The three database files are created automatically in `data/` on first run. They are gitignored.

---

## Example Questions

| Category | Question |
|---|---|
| Standings | Who is leading the UCI WorldTour? |
| Riders | What are Tadej Pogačar's career stats? |
| Riders | Show me Remco Evenepoel's 2026 results |
| Races | Who won the 2026 Giro d'Italia? |
| Stages | What happened in stage 10 of the Tour de France 2026? |
| Startlists | Who is riding the Tour de France 2026? |
| News | What is the latest news about Jonas Vingegaard? |
| Live | What is happening in the race right now? |
| Follow-up | And what is the time gap to second place? |
| Follow-up | Tell me more about the stage winner |
| Pronoun | What did he win this spring? *(resolves to the last rider discussed)* |
| Comparison | Who is better between them? *(resolves both riders from context)* |

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message + persistent model button |
| `/help` | Full list of example questions by category |
| `/status` | Current WorldTour top 5 |
| `/model` | Switch AI model with inline buttons |
| `⚙️ Change Model` | Persistent keyboard button — same as `/model` |
| Any text | Runs the full agent pipeline; follow-ups remember context |

---

## Known Limitations

- **Model state is in-memory.** Restarting `bot.py` resets model choice back to Claude Sonnet, but conversation history and user profiles survive (they're in SQLite).
- **Firecrawl is for live races only.** 500 free pages/month. Only called when a race is actively happening.
- **Playwright requires Chromium.** Run `playwright install chromium` once.
- **Groq tool-call reliability.** Llama 3.3 occasionally generates tool calls in non-standard formats (malformed wrappers, CDATA-encoded fields). The agent recovers automatically — answers may degrade gracefully but won't crash. Claude models don't have this issue.
- **Groq rate limits.** Free tier has token-per-minute limits — wait a moment and retry if you hit them.
- **Resolver adds one extra LLM call.** On the first question of a session (no history yet) the resolver passes the question through unchanged at minimal cost. On follow-ups it rewrites pronouns and vague references before the planner runs.
- **Summarization threshold is 20 messages.** Below that, full history is sent every request.

---

## Playground

`playground.ipynb` lets you test and inspect every part of the agent without Telegram:

| Section | What it shows |
|---|---|
| Steps 0–7 | Full pipeline: planner → executor → synthesizer, raw tool outputs, rendered answers |
| **Step 8** | **Memory inspection** — query all three SQLite databases directly, see the exact prompt the model receives, trigger a session handoff manually |
| Cleanup | Reset all databases (full wipe or per-chat) without file-lock errors |

---

## Tech Stack

| | |
|---|---|
| [LangGraph](https://langchain-ai.github.io/langgraph/) | StateGraph orchestration + SqliteSaver checkpointing |
| [Anthropic SDK](https://anthropic.com) | Claude Sonnet 4 and Haiku 4.5 |
| [Groq](https://console.groq.com) | Llama 3.3 70b via OpenAI-compatible SDK |
| [Tavily](https://tavily.com) | Web search for results, standings, and news |
| [Firecrawl](https://firecrawl.dev) | Headless browser for live JS-rendered race pages |
| [Playwright](https://playwright.dev) | Chromium scraping for real-time race situation data |
| [python-telegram-bot](https://python-telegram-bot.org/) | Async Telegram bot framework |
| [Pydantic v2](https://docs.pydantic.dev) | Data schemas and validation |
| [Rich](https://github.com/Textualize/rich) | Terminal UI for CLI mode |

---

## Other Branches

| Branch | What it is |
|---|---|
| [`cycling-agent`](../../tree/cycling-agent) | Original cycling agent — Claude only |
| [`groq-migration`](../../tree/groq-migration) | Cycling agent with Groq Llama 3.3 70b |
| [`feature/model-fusion`](../../tree/feature/model-fusion) | Multi-model support — Claude + Groq switchable via `/model` |
| [`feature/langgraph-memory`](../../tree/feature/langgraph-memory) | **This branch** — LangGraph + persistent memory + pronoun resolution + user profiles |

---

## License

MIT
