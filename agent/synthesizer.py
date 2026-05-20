from anthropic import Anthropic
from models.answer import CyclingAnswer

client = Anthropic()

SYSTEM_PROMPT = """You are a knowledgeable professional cycling commentator and analyst.
You have been given raw data fetched from procyclingstats.com and web searches.
Synthesize this into a clear, accurate, engaging answer.

Guidelines:
- Be precise with numbers, dates, and rider names
- Use proper cycling terminology naturally (GC, peloton, domestique, jersey, etc.)
- If data is missing or a race hasn't happened yet, say so clearly — never invent facts
- Suggest 2-3 relevant follow-up questions the user would genuinely find interesting
- Keep the main answer concise but complete (3-6 sentences for simple questions)
- Set confidence to "low" if data seems outdated, incomplete, or contradictory
- Set confidence to "high" only when you have complete, structured PCS data
- Always fill source_note with where the data came from (e.g. "procyclingstats.com" or "web search")"""


def synthesize(question: str, raw_findings: dict[str, str]) -> CyclingAnswer:
    findings_text = "\n\n---\n\n".join(
        f"**{topic}**\n{content}" for topic, content in raw_findings.items()
    )

    tools = [
        {
            "name": "submit_cycling_answer",
            "description": "Submit the final structured cycling answer",
            "input_schema": CyclingAnswer.model_json_schema(),
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
                "content": f"Question: {question}\n\nResearch findings:\n\n{findings_text}",
            }
        ],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    return CyclingAnswer(**tool_block.input)
