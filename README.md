# Pro Cycling Intelligence Agent

A conversational AI agent that answers natural language questions about professional cycling — standings, race results, rider profiles, stage data, and live race updates — delivered via a Telegram bot or CLI.

Built with the **Plan & Execute** agent pattern. Supports **Claude Sonnet 4**, **Claude Haiku 4.5**, and **Llama 3.3 70b on Groq** — switchable live inside Telegram with a single tap.

> **Branch:** `feature/model-fusion` — unified multi-model support. Switch between Claude Sonnet, Claude Haiku, and Groq Llama 3.3 per chat session without restarting.

---

## What It Does

Ask it anything about pro cycling and it will:
1. **Plan** — the active LLM decides which tools to use and in what order
2. **Execute** — fetches data using the right tool for the job (no AI in this step)
3. **Synthesize** — the active LLM turns raw findings into a clear, structured answer

---

## Architecture

```
Question
    │
    ▼
┌──────────┐
│ PLANNER  │  Active model generates a 2–5 step research plan
└────┬─────┘
     │
     ▼
┌──────────┐
│ EXECUTOR │  Runs each step — Tavily search, Firecrawl/Playwright scrape, or static scrape (no AI)
└────┬─────┘
     │
     ▼
┌──────────────┐
│ SYNTHESIZER  │  Active model reads findings and returns a typed CyclingAnswer
└────┬─────────┘
     │
     ▼
 CyclingAnswer ✓
```

---

## Models

Switch models live in Telegram with the **⚙️ Change Model** button or the `/model` command. Each chat session remembers its own choice independently.

| Key | Model | Provider | Notes |
|---|---|---|---|
| `sonnet` | `claude-sonnet-4-6` | Anthropic | Default — best quality |
| `haiku` | `claude-haiku-4-5-20251001` | Anthropic | Faster and cheaper |
| `groq` | `llama-3.3-70b-versatile` | Groq | Free tier, very fast |

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
| `firecrawl` | Live race data happening right now | Firecrawl headless browser + Playwright |

**Firecrawl** is reserved for mid-race live data. When you ask about the current race situation, groups, or time gaps, it uses **Playwright** (headless Chromium) to scrape the live PCS page and returns real-time rider groups, time gaps, and timeline updates. Firecrawl is the fallback if Playwright times out.

---

## Setup

```bash
# 1. Clone and install
pip install -r requirements.txt
playwright install chromium

# 2. Get your API keys
# - Anthropic: https://console.anthropic.com
# - Groq:      https://console.groq.com  (free)
# - Tavily:    https://tavily.com
# - Firecrawl: https://firecrawl.dev     (500 pages/month free)
# - Telegram:  message @BotFather → /newbot → copy the token

# 3. Configure
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, GROQ_API_KEY, TAVILY_API_KEY, FIRECRAWL_API_KEY, TELEGRAM_BOT_TOKEN

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
| Races | Who won the 2026 Giro d'Italia? | `pcs_race` |
| Races | What were the GC results at Paris-Roubaix? | `search` |
| Stages | What happened in stage 10 of the Tour de France 2026? | `pcs_stage` |
| Startlists | Who is riding the Tour de France 2026? | `pcs_startlist` |
| News | What is the latest news about Jonas Vingegaard? | `search` |
| Live | What is happening in the race right now? | `firecrawl` |
| Live | Who is in the breakaway and what is the gap? | `firecrawl` |

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message, example questions, and persistent model button |
| `/help` | Full list of example questions by category |
| `/status` | Current WorldTour top 5 |
| `/model` | Switch AI model with inline buttons |
| `⚙️ Change Model` | Persistent keyboard button — same as `/model` |
| Any text | Runs the full agent pipeline with the active model |

---

## Known Limitations

- **Firecrawl is for live races only.** It uses your 500 free pages/month. The agent only calls it when a race is actively happening and you ask for live data.
- **Playwright requires Chromium.** Run `playwright install chromium` once after installing requirements.
- **Slug precision matters.** The planner converts common names to slugs (e.g. "TDF" → "tour-de-france") but unusual races may not be recognized. Try using the full official race name.
- **Future races return no results.** If a race hasn't happened yet, the agent will say so clearly rather than guessing.
- **Groq rate limits.** The free Groq tier has token-per-minute limits. Under heavy use you may occasionally see a rate limit error — wait a few seconds and retry.
- **Model state is in-memory.** Restarting `bot.py` resets all chats back to Claude Sonnet.

---

## Tech Stack

| | |
|---|---|
| [Anthropic SDK](https://anthropic.com) | Claude Sonnet 4 and Haiku 4.5 for planning and synthesis |
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
| [`cycling-agent`](../../tree/cycling-agent) | Cycling agent with Claude (Anthropic) only |
| [`groq-migration`](../../tree/groq-migration) | Same cycling agent with LLM swapped to Llama 3.3 70b on Groq |
| [`feature/model-fusion`](../../tree/feature/model-fusion) | **This branch** — unified multi-model with live switcher |

---

## License

MIT
