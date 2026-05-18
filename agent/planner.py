import json
from anthropic import Anthropic
from models.plan import ResearchPlan
from tools.cycling_pcs import COMMON_RACE_SLUGS

client = Anthropic()

SYSTEM_PROMPT = f"""You are a professional cycling data analyst assistant.
Given a user's question about professional cycling, create a focused research plan
to gather the data needed to answer it precisely.

Available tools and query formats:
- pcs_ranking   : UCI WorldTour standings (Tavily search). Query: "20" for top 20 individuals, "team/20" for top 20 teams
- pcs_rider     : Full rider profile (Tavily search). Query: rider slug e.g. "tadej-pogacar"
- pcs_race      : Race overview and GC results (Tavily search). Query: "race-slug/year" e.g. "tour-de-france/2026"
- pcs_stage     : Single stage results (Tavily search). Query: "race-slug/year/stage-number" e.g. "tour-de-france/2026/3"
- pcs_startlist : Race startlist (Tavily search). Query: "race-slug/year" e.g. "giro-d-italia/2026"
- pcs_rider_results : Rider's season results (Tavily search). Query: "rider-slug/year" e.g. "remco-evenepoel/2026"
- search        : Tavily web search for general news and information. Query: search string
- scrape        : Scrape a static HTML page. Query: full URL
- firecrawl     : Scrape a live JS-rendered page — ONLY use when the user wants data from a race
                  actively happening RIGHT NOW (live ticker, km remaining, gap updates mid-race).
                  Query formats:
                    "live/race-slug/year"      → live ticker for an ongoing race
                    "gc/race-slug/year"         → GC standings mid-race
                    "stage/race-slug/year/N"   → specific stage page
                    "ranking"                   → WorldTour ranking page
                    "https://..."               → any direct URL

Rules:
- Generate 2 to 5 targeted steps — no more
- Use pcs_* tools for historical data and career stats
- Use search for recent results, current standings, news, and "who is leading" — Tavily handles these well
- Use firecrawl ONLY when the user asks about something happening RIGHT NOW mid-race: "live", "right now", "what km are they at", "live ticker" — NOT just because the word "current" or "leading" appears
- Always use the correct slug format — convert common names using the reference below
- Current year is 2026

Common race slug reference:
{json.dumps(COMMON_RACE_SLUGS, indent=2)}
"""


def create_plan(question: str) -> ResearchPlan:
    tools = [
        {
            "name": "submit_research_plan",
            "description": "Submit the structured research plan",
            "input_schema": ResearchPlan.model_json_schema(),
        }
    ]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        tools=tools,
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": question}],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    return ResearchPlan(**tool_block.input)
