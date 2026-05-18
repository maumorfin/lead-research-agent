import json
from anthropic import Anthropic
from models.plan import ResearchPlan
from tools.cycling_pcs import COMMON_RACE_SLUGS

client = Anthropic()

SYSTEM_PROMPT = f"""You are a professional cycling data analyst assistant.
Given a user's question about professional cycling, create a focused research plan
to gather the data needed to answer it precisely.

Available tools and query formats:
- pcs_ranking   : UCI WorldTour standings. Query: "20" for top 20 individuals, "team/20" for top 20 teams
- pcs_rider     : Full rider profile. Query: rider slug e.g. "tadej-pogacar"
- pcs_race      : Race overview and GC results. Query: "race-slug/year" e.g. "tour-de-france/2025"
- pcs_stage     : Single stage results. Query: "race-slug/year/stage-number" e.g. "tour-de-france/2025/3"
- pcs_startlist : Race startlist. Query: "race-slug/year" e.g. "giro-d-italia/2025"
- pcs_rider_results : Rider's season results. Query: "rider-slug/year" e.g. "remco-evenepoel/2025"
- search        : Tavily web search for live news, ongoing races, or anything not in PCS. Query: search string
- scrape        : Scrape a specific URL directly. Query: full URL

Rules:
- Generate 2 to 5 targeted steps — no more
- Prefer PCS tools for historical and structured data
- Use search for live updates, races currently in progress, or recent news
- Always use the correct slug format — convert common names using the reference below
- Current year is 2025

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
