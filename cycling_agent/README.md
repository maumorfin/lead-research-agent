# Pro Cycling Intelligence Agent

A conversational AI agent that answers natural language questions about professional cycling — standings, race results, rider profiles, stage data — delivered via a Telegram bot or CLI.

Built with the **Plan & Execute** agent pattern using Claude, procyclingstats.com, and Tavily.

---

## What It Does

Ask it anything about pro cycling and it will:
1. **Plan** — Claude decides what data sources to query
2. **Execute** — fetches structured data from procyclingstats.com and web search
3. **Synthesize** — Claude turns raw data into a clear, accurate answer

---

## Architecture

```
Question
    │
    ▼
┌──────────┐
│ PLANNER  │  Claude generates a 2–5 step research plan
└────┬─────┘
     │
     ▼
┌──────────┐
│ EXECUTOR │  Runs each step — PCS data, web search, or scraping (no AI)
└────┬─────┘
     │
     ▼
┌──────────────┐
│ SYNTHESIZER  │  Claude reads findings and returns a typed CyclingAnswer
└────┬─────────┘
     │
     ▼
 CyclingAnswer ✓
```

---

## Setup

```bash
# 1. Clone and install
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Get your Telegram bot token
# Message @BotFather on Telegram → /newbot → copy the token

# 3. Configure
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, TAVILY_API_KEY, TELEGRAM_BOT_TOKEN

# 4. Test via CLI first (no Telegram needed)
python main.py "Who leads the WorldTour?"

# 5. Run the bot
python bot.py
```

---

## Example Questions

| Category | Question |
|---|---|
| Standings | Who is leading the UCI WorldTour right now? |
| Standings | Show me the top 10 WorldTour teams |
| Riders | What are Tadej Pogačar's career stats? |
| Riders | Show me Remco Evenepoel's 2025 results |
| Races | Who won the 2025 Giro d'Italia? |
| Races | What were the GC results at Paris-Roubaix? |
| Stages | What happened in stage 10 of the Tour de France 2025? |
| Stages | Who won stage 1 of the Vuelta a España 2025? |
| Startlists | Who is riding the Tour de France 2025? |
| News | What is the latest news about Jonas Vingegaard? |

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message and example questions |
| `/help` | Full list of example questions by category |
| `/status` | Current WorldTour top 5 (cached for 1 hour) |
| Any text | Runs the full agent pipeline |

---

## Known Limitations

- **PCS data is not real-time.** procyclingstats.com is updated after stages finish, not during. For live race updates, the agent automatically falls back to Tavily web search.
- **Slug precision matters.** The planner converts common names to slugs (e.g. "TDF" → "tour-de-france") but unusual races may not be recognized. Try using the full official race name.
- **Future races return no results.** If a race hasn't happened yet, the agent will say so clearly rather than guessing.
- **PCS coverage.** Some smaller races or very old results may not be on procyclingstats.com. The agent falls back to web search in those cases.

---

## Tech Stack

| | |
|---|---|
| [Anthropic SDK](https://anthropic.com) | Claude `claude-sonnet-4-6` for planning and synthesis |
| [procyclingstats](https://pypi.org/project/procyclingstats/) | Structured cycling data from procyclingstats.com |
| [Tavily](https://tavily.com) | Web search for live news and updates |
| [python-telegram-bot](https://python-telegram-bot.org/) | Async Telegram bot framework |
| [Pydantic v2](https://docs.pydantic.dev) | Data schemas and validation |
| [Rich](https://github.com/Textualize/rich) | Terminal UI for CLI mode |

---

## License

MIT
