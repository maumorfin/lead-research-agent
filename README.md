# Lead Research Agent

An AI agent that takes a list of company names, autonomously researches each one across the web, and returns a structured, scored lead profile — ready for your sales team.

Built with the **Plan & Execute** agent pattern using the Anthropic SDK and Tavily.

---

## What Problem Does It Solve?

You come back from a conference with 20 business cards. Instead of spending a day Googling each company manually — finding the CEO, checking funding, guessing team size — you run one command and get a scored profile for every company in minutes.

This is the kind of repetitive, research-heavy work that agents are built for.

---

## What is an Agent?

A regular AI interaction is one turn: you ask, it answers.

An **agent** is different — it receives a goal, breaks it into steps, uses tools to gather information, and synthesizes a result. It decides *how* to get there. You give it a company name; it figures out what to search for, runs the searches, reads the results, and produces a report.

This project uses the **Plan & Execute** pattern, one of the most reliable ways to structure an agent:

```
Company Name
     │
     ▼
┌─────────────┐
│   PLANNER   │  Claude decides what to research: 5–8 targeted steps.
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  EXECUTOR   │  Runs each step using web search or page scraping.
│             │  No AI here — just a for loop calling tools.
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ SYNTHESIZER │  Claude reads all findings and outputs a typed, scored LeadProfile.
└──────┬──────┘
       │
       ▼
  LeadProfile ✓
```

Keeping planning and execution separate makes the agent predictable, cheap to run, and easy to debug — you can inspect the plan before anything executes.

---

## Project Structure

```
AI_Agent/
├── main.py                  # Entry point — orchestration and terminal UI
├── requirements.txt
│
├── models/
│   ├── plan.py              # ResearchPlan schema (planner output)
│   └── lead.py              # LeadProfile schema (final output)
│
├── tools/
│   ├── web_search.py        # Tavily search wrapper
│   └── web_scraper.py       # Page scraper (httpx + BeautifulSoup)
│
└── agent/
    ├── planner.py           # Phase 1 — Claude generates the research plan
    ├── executor.py          # Phase 2 — runs each step with the right tool
    └── synthesizer.py       # Phase 3 — Claude synthesizes findings into LeadProfile
```

---

## Setup

**1. Clone and install**

```bash
git clone https://github.com/YOUR_USERNAME/lead-research-agent.git
cd lead-research-agent
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**2. Add your API keys**

```bash
cp .env.example .env
# Open .env and fill in both keys
```

| Key | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) — free $5 credit on signup |
| `TAVILY_API_KEY` | [app.tavily.com](https://app.tavily.com) — free tier: 1,000 searches/month |

**3. Run**

```bash
# Built-in sample companies
python main.py

# Your own list
python main.py "Notion" "Figma" "Linear"
```

---

## Example Output

```
╭──────────────────── Lead Research Agent ────────────────────╮
│ Researching 3 companies: Notion, Figma, Linear              │
╰─────────────────────────────────────────────────────────────╯

╭─ Score: 8.5/10 ─────────────────────────────────────────────╮
│ Notion                                                       │
│ All-in-one workspace for notes, docs, and project mgmt      │
│                                                              │
│ Industry: Productivity SaaS | Size: 500–1000 | Founded: 2016│
│ Funding: $275M Series C | Hiring: Yes                        │
╰─────────────────────────────────────────────────────────────╯

Key People:
  • Ivan Zhao — CEO & Co-founder
  • Simon Last — CTO & Co-founder

Tech Stack: React, Node.js, PostgreSQL, Electron

Talking Points:
  → Expanding into enterprise — likely evaluating dev partners
  → Active backend hiring signals scaling pressure
  → Ivan Zhao vocal about flexibility — angle for custom tooling

┌──────────────────────────────────────────────────────┐
│ Company │ Industry          │ Score │ Verdict         │
│ Notion  │ Productivity SaaS │  8.5  │ ✓ Pursue        │
│ Figma   │ Design Tools      │  7.2  │ ✓ Pursue        │
│ Linear  │ Dev Tools         │  5.8  │ ~ Maybe         │
└──────────────────────────────────────────────────────┘
```

---

## Exploring with the Notebook

A Jupyter notebook (`playground.ipynb`) lets you run each phase individually and inspect the output at every step — the plan Claude generates, the raw web findings, and the final profile.

```bash
jupyter notebook playground.ipynb
```

---

## Ideas to Extend This

- **CSV input/output** — read companies from a file, write profiles back to one
- **Cold email generation** — add a fourth phase that drafts a personalized outreach email
- **Async execution** — run all research steps in parallel with `asyncio`
- **Custom scoring** — pass your own ICP criteria to the synthesizer system prompt
- **Caching** — persist raw findings so you don't re-research the same company twice

---

## Tech Stack

| | |
|---|---|
| [Anthropic SDK](https://anthropic.com) | Claude `claude-sonnet-4-6` for planning and synthesis |
| [Tavily](https://tavily.com) | Web search built for AI agents |
| [Pydantic v2](https://docs.pydantic.dev) | Data schemas and validation |
| [httpx](https://www.python-httpx.org) + [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) | Page scraping |
| [Rich](https://github.com/Textualize/rich) | Terminal UI |

---

## Other Branches

This repo has two more agents on separate branches — same Plan & Execute pattern, different domain.

| Branch | What it is |
|---|---|
| [`cycling-agent`](../../tree/cycling-agent) | **Pro Cycling Intelligence Agent** — answers natural language questions about professional cycling via a Telegram bot or CLI. Uses Claude for planning and synthesis, Tavily for web search, and Firecrawl for live JS-rendered race pages. |
| [`groq-migration`](../../tree/groq-migration) | Same cycling agent with the LLM swapped from Claude to **Llama 3.3 70b on Groq** via the OpenAI-compatible SDK. Faster and free to run. |
| [`feature/model-fusion`](../../tree/feature/model-fusion) | Cycling agent with **multi-model support** — Claude Sonnet, Claude Haiku, and Groq switchable live inside Telegram with a `/model` command and persistent keyboard button. |
| [`feature/langgraph-memory`](../../tree/feature/langgraph-memory) | **LangGraph refactor** — persistent in-thread memory (SqliteSaver), pronoun resolution ("he" → rider name), conversational synthesizer tone, 2-hour session management, and long-term user profiles in SQLite. |

---

## License

MIT
