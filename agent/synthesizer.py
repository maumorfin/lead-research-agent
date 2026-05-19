import os
import json
from openai import OpenAI
from models.answer import CyclingAnswer

client = OpenAI(
    api_key=os.environ["GROQ_API_KEY"],
    base_url="https://api.groq.com/openai/v1",
)

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
- Set confidence to "high" only when you have complete, structured data
- Always fill source_note with where the data came from"""


def synthesize(question: str, raw_findings: dict[str, str]) -> CyclingAnswer:
    findings_text = "\n\n---\n\n".join(
        f"**{topic}**\n{content}" for topic, content in raw_findings.items()
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "submit_cycling_answer",
                "description": "Submit the final structured cycling answer",
                "parameters": CyclingAnswer.model_json_schema(),
            },
        }
    ]

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Question: {question}\n\nResearch findings:\n\n{findings_text}",
            },
        ],
        tools=tools,
        tool_choice="required",
    )

    tool_call = response.choices[0].message.tool_calls[0]
    data = json.loads(tool_call.function.arguments)
    return CyclingAnswer(**data)
