import json
from config import get_model
from agent.llm_client import call_llm
from models.plan import ResearchPlan
from tools.cycling_pcs import COMMON_RACE_SLUGS

SYSTEM_PROMPT = f"""You are a professional cycling data analyst assistant.
Given a user's question about professional cycling, create a focused research plan
to gather the data needed to answer it precisely.

Available tools:
- pcs_ranking: UCI WorldTour standings. Query: "20" for top 20 individuals, "team/20" for teams
- pcs_rider: Rider profile. Query: rider slug e.g. "tadej-pogacar"
- pcs_race: Race overview and GC. Query: "race-slug/year" e.g. "tour-de-france/2026"
- pcs_stage: Stage results. Query: "race-slug/year/stage-number" e.g. "tour-de-france/2026/3"
- pcs_startlist: Race startlist. Query: "race-slug/year"
- pcs_rider_results: Rider season results. Query: "rider-slug/year" e.g. "tadej-pogacar/2026"
- search: Tavily web search for news and general information
- scrape: Scrape a static HTML page. Query: full URL
- firecrawl: Scrape JS-rendered pages.
  Query formats:
    "situation/race-slug/year/N"  → LIVE groups, time gaps, riders right now (Playwright — most accurate)
    "live/race-slug/year"         → full race-level live ticker page
    "stage-live/race-slug/year/N" → live ticker for a specific stage
    "gc/race-slug/year"           → GC standings mid-race
    "stage/race-slug/year/N"      → specific stage page
    "ranking"                     → WorldTour ranking page
    "https://..."                 → any direct URL

  Use "situation/..." when the user asks about the current race situation, live groups,
  time gaps, who is in the breakaway, what km are left, or anything happening right now mid-stage.

Rules:
- Generate 2 to 5 targeted steps — no more
- Use pcs_* tools for historical data and career stats
- Use search for recent results, current standings, news, and "who is leading" — Tavily handles these well
- Use firecrawl ONLY when the user asks about something happening RIGHT NOW mid-race
- Always use the correct slug format — convert common names using the reference below
- Current year is 2026

Common race slugs:
{json.dumps(COMMON_RACE_SLUGS, indent=2)}
"""

# Flat schema — no $defs/$ref so it works with both Anthropic and Groq
_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "The original user question"},
        "steps": {
            "type": "array",
            "description": "2 to 5 targeted research steps",
            "items": {
                "type": "object",
                "properties": {
                    "step_id": {"type": "integer"},
                    "description": {"type": "string", "description": "What this step is trying to find out"},
                    "tool": {
                        "type": "string",
                        "enum": [
                            "pcs_ranking", "pcs_rider", "pcs_race", "pcs_stage",
                            "pcs_startlist", "pcs_rider_results", "search", "scrape", "firecrawl",
                        ],
                    },
                    "query": {"type": "string", "description": "Slug, URL, or search string — see format per tool in system prompt"},
                },
                "required": ["step_id", "description", "tool", "query"],
            },
        },
    },
    "required": ["question", "steps"],
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_research_plan",
            "description": "Submit the structured research plan for execution",
            "parameters": _PLAN_SCHEMA,
        },
    }
]


def create_plan(question: str, chat_id: int = 0) -> ResearchPlan:
    result = call_llm(
        model_config=get_model(chat_id),
        system_prompt=SYSTEM_PROMPT,
        user_message=question,
        tools=TOOLS,
        max_tokens=2000,
    )
    return ResearchPlan(**result["input"])
