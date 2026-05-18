from anthropic import Anthropic
from models.plan import ResearchPlan

client = Anthropic()

SYSTEM_PROMPT = """You are a B2B sales research strategist.
Given a company name, create a concise, focused research plan to qualify it as a potential client lead.

Focus your research on:
- Company overview (what they do, who they serve)
- Size and growth signals (headcount, funding, hiring)
- Key decision-makers (CEO, CTO, Head of Engineering)
- Tech stack (what tools and languages they use)
- Recent news or milestones (launches, funding rounds, expansions)

Generate between 5 and 8 targeted steps. Prefer specific, high-signal search queries."""


def create_plan(company_name: str) -> ResearchPlan:
    tools = [
        {
            "name": "submit_research_plan",
            "description": "Submit the structured research plan for execution",
            "input_schema": ResearchPlan.model_json_schema(),
        }
    ]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        tools=tools,
        tool_choice={"type": "any"},
        messages=[
            {
                "role": "user",
                "content": f"Create a research plan to qualify this company as a lead: {company_name}",
            }
        ],
    )

    tool_use_block = next(b for b in response.content if b.type == "tool_use")
    return ResearchPlan(**tool_use_block.input)
