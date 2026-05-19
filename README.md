# Pro Cycling Intelligence Agent

A conversational AI agent that answers natural language questions about professional cycling — standings, race results, rider profiles, stage data, and live race updates — delivered via a Telegram bot or CLI.

Built with the **Plan & Execute** agent pattern using **Llama 3.3 70b on Groq**, Tavily, and Firecrawl.

> **Branch:** `groq-migration` — LLM migrated from Anthropic Claude to Groq (llama-3.3-70b-versatile) via the OpenAI-compatible SDK.

---

## What It Does

Ask it anything about pro cycling and it will:
1. **Plan** — Llama 3.3 70b decides which tools to use and in what order
2. **Execute** — fetches data using the right tool for the job (no AI in this step)
3. **Synthesize** — Llama 3.3 70b turns raw findings into a clear, structured answer

---

## Architecture

```
Question
    │
    ▼
┌──────────┐
│ PLANNER  │  Llama 3.3 70b (Groq) generates a 2–5 step research plan
└────┬─────┘
     │
     ▼
┌──────────┐
│ EXECUTOR │  Runs each step — Tavily search, Firecrawl scrape, or static scrape (no AI)
└────┬─────┘
     │
     ▼
┌──────────────┐
│ SYNTHESIZER  │  Llama 3.3 70b (Groq) reads findings and returns a typed CyclingAnswer
└────┬─────────┘
     │
     ▼
 CyclingAnswer ✓
```

---

## Tools

The agent picks the right tool automatically based on the question:

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
| `firecrawl` | Live race data happening right now | Firecrawl headless browser |

**Firecrawl** is reserved for mid-race live data (live ticker, gaps, km remaining). It can scrape both the race-level live page and the per-stage live ticker (`/stage-N/live`). For everything else — standings, recent results, news — Tavily handles it.

---

## Setup

```bash
# 1. Clone and install
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Get your API keys
# - Groq:      https://console.groq.com  (free)
# - Tavily:    https://tavily.com
# - Firecrawl: https://firecrawl.dev     (500 pages/month free)
# - Telegram:  message @BotFather → /newbot → copy the token

# 3. Configure
cp .env.example .env
# Fill in GROQ_API_KEY, TAVILY_API_KEY, FIRECRAWL_API_KEY, TELEGRAM_BOT_TOKEN

# 4. Test via CLI first (no Telegram needed)
python main.py "Who leads the WorldTour?"

# 5. Run the bot
python bot.py
```

---

## Example Questions

| Category | Question | Tool used |
|---|---|---|
| Standings | Who is leading the UCI WorldTour? | `pcs_ranking` |
| Standings | Show me the top 10 WorldTour teams | `pcs_ranking` |
| Riders | What are Tadej Pogačar's career stats? | `pcs_rider` |
| Riders | Show me Remco Evenepoel's 2026 results | `pcs_rider_results` |
| Races | Who won the 2025 Giro d'Italia? | `pcs_race` |
| Races | What were the GC results at Paris-Roubaix? | `search` |
| Stages | What happened in stage 10 of the Tour de France 2025? | `pcs_stage` |
| Startlists | Who is riding the Tour de France 2026? | `pcs_startlist` |
| News | What is the latest news about Jonas Vingegaard? | `search` |
| Live | What is happening in the race right now? | `firecrawl` |
| Live | Show me the live stage 10 ticker | `firecrawl` |

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message and example questions |
| `/help` | Full list of example questions by category |
| `/status` | Current WorldTour top 5 |
| Any text | Runs the full agent pipeline |

---

## Known Limitations

- **Firecrawl is for live races only.** It uses your 500 free pages/month. The agent only calls it when a race is actively happening and you ask for live data.
- **Slug precision matters.** The planner converts common names to slugs (e.g. "TDF" → "tour-de-france") but unusual races may not be recognized. Try using the full official race name.
- **Future races return no results.** If a race hasn't happened yet, the agent will say so clearly rather than guessing.
- **Groq rate limits.** The free Groq tier has token-per-minute limits. Under heavy use you may occasionally see a rate limit error — wait a few seconds and retry.

---

## Tech Stack

| | |
|---|---|
| [Groq](https://console.groq.com) | `llama-3.3-70b-versatile` for planning and synthesis (via OpenAI-compatible SDK) |
| [Tavily](https://tavily.com) | Web search for results, standings, and news |
| [Firecrawl](https://firecrawl.dev) | Headless browser for live JS-rendered race pages |
| [python-telegram-bot](https://python-telegram-bot.org/) | Async Telegram bot framework |
| [Pydantic v2](https://docs.pydantic.dev) | Data schemas and validation |
| [Rich](https://github.com/Textualize/rich) | Terminal UI for CLI mode |

---

## License

MIT
