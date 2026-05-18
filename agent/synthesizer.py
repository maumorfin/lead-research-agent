from anthropic import Anthropic
from models.lead import LeadProfile

client = Anthropic()

SYSTEM_PROMPT = """You are a B2B sales analyst reviewing raw research about a company.
Your job is to extract key facts and produce a structured lead profile.

Score the lead from 0 to 10 based on:
- Company size and growth trajectory (larger / faster growing = higher score)
- Budget signals: funding rounds, revenue mentions, or enterprise clients
- Visibility of decision-makers (named CTO/VP Eng = easier to reach)
- Relevance to a software development agency (do they buy tech services?)

Score conservatively: 7+ means actively worth a cold email. Be factual — if you did not find something, leave it null."""


def synthesize(company_name: str, raw_findings: dict[str, str]) -> LeadProfile:
    findings_text = "\n\n---\n\n".join(
        f"**{topic}**\n{content}" for topic, content in raw_findings.items()
    )

    tools = [
        {
            "name": "submit_lead_profile",
            "description": "Submit the structured lead profile",
            "input_schema": LeadProfile.model_json_schema(),
        }
    ]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        tools=tools,
        tool_choice={"type": "any"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Company: {company_name}\n\n"
                    f"Raw research findings:\n\n{findings_text}"
                ),
            }
        ],
    )

    tool_use_block = next(b for b in response.content if b.type == "tool_use")
    return LeadProfile(**tool_use_block.input)
