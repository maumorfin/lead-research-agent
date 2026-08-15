from config import get_model
from agent.llm_client import call_llm
from models.answer import CyclingAnswer

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

# Flat schema — no $defs/$ref so it works with both Anthropic and Groq
_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "The original user question"},
        "answer": {"type": "string", "description": "Main answer in clear prose, 3-6 sentences"},
        "data_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Key facts as short bullet points",
        },
        "source_note": {"type": "string", "description": "Where the data came from"},
        "follow_up_suggestions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "2-3 related questions the user might ask next",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "high=complete fresh data, medium=partial, low=outdated or missing",
        },
    },
    "required": ["question", "answer", "data_points", "follow_up_suggestions", "confidence"],
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_cycling_answer",
            "description": "Submit the final structured cycling answer",
            "parameters": _ANSWER_SCHEMA,
        },
    }
]


def synthesize(question: str, raw_findings: dict[str, str], chat_id: int = 0) -> CyclingAnswer:
    findings_text = "\n\n---\n\n".join(
        f"**{topic}**\n{content}" for topic, content in raw_findings.items()
    )
    result = call_llm(
        model_config=get_model(chat_id),
        system_prompt=SYSTEM_PROMPT,
        user_message=f"Question: {question}\n\nResearch findings:\n\n{findings_text}",
        tools=TOOLS,
        max_tokens=3000,
    )
    return CyclingAnswer(**result["input"])
