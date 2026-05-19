import os
import json
from openai import OpenAI
from models.plan import ResearchPlan
from tools.cycling_pcs import COMMON_RACE_SLUGS

client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)

SYSTEM_PROMPT = f"""You are a professional cycling data analyst assistant.
Given a user's question about professional cycling, create a focused research plan
to gather the data needed to answer it precisely.

Available tools:
- pcs_ranking: UCI WorldTour standings. Query: "20" for top 20 individuals, "team/20" for teams
- pcs_rider: Full rider profile. Query: rider slug e.g. "tadej-pogacar"
- pcs_race: Race overview and GC results. Query: "race-slug/year" e.g. "tour-de-france/2026"
- pcs_stage: Single stage results. Query: "race-slug/year/stage-number" e.g. "tour-de-france/2026/3"
- pcs_startlist: Race startlist. Query: "race-slug/year"
- pcs_rider_results: Rider season results. Query: "rider-slug/year" e.g. "tadej-pogacar/2026"
- search: Tavily web search for news and general information
- scrape: Scrape a static HTML page (query: full URL)
- firecrawl: Scrape JS-rendered pages — use for live race data happening RIGHT NOW mid-race.
  Query formats:
    "live/race-slug/year"         → race-level live ticker
    "stage-live/race-slug/year/N" → live ticker for a specific stage (e.g. "stage-live/giro-d-italia/2026/10")
    "gc/race-slug/year"           → current GC standings
    "stage/race-slug/year/N"      → completed stage results page
    "ranking"                     → current WorldTour ranking
    "https://..."                 → any direct URL

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
            "type": "function",
            "function": {
                "name": "submit_research_plan",
                "description": "Submit the structured research plan for execution",
                "parameters": ResearchPlan.model_json_schema(),
            },
        }
    ]

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        tools=tools,
        tool_choice="required",
    )

    tool_call = response.choices[0].message.tool_calls[0]
    data = json.loads(tool_call.function.arguments)
    return ResearchPlan(**data)
