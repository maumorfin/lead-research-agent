from memory.user_store import UserStore
from config import get_model
from agent.llm_client import call_llm


EXTRACTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_session_facts",
            "description": "Save extracted facts from this conversation",
            "parameters": {
                "type": "object",
                "properties": {
                    "riders": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Rider slugs mentioned e.g. tadej-pogacar",
                    },
                    "races": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Race slugs mentioned e.g. giro-d-italia",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language the user wrote in e.g. de, en, it",
                    },
                    "summary": {
                        "type": "string",
                        "description": "One sentence summary of what was discussed",
                    },
                },
                "required": ["riders", "races", "language", "summary"],
            },
        },
    }
]

EXTRACTION_PROMPT = """You are extracting facts from a cycling conversation to save to a user profile.
Extract: riders mentioned, races discussed, the user's language, and a one-sentence summary.
Be concise. Use slug format for riders and races (e.g. tadej-pogacar, giro-d-italia)."""


def run_handoff(
    old_thread_id: str,
    chat_id: int,
    app,
    user_store: UserStore,
):
    """
    Extract facts from the expired thread and save to long-term user profile.
    Called lazily when the user sends their first message after a timeout.
    """
    try:
        state = app.get_state(
            config={"configurable": {"thread_id": old_thread_id}}
        )
        if not state or not state.values.get("messages"):
            return

        messages = state.values["messages"]
        if len(messages) < 2:
            return

        conversation = "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in messages
            if isinstance(m, dict)
        )

        result = call_llm(
            model_config=get_model(chat_id),
            system_prompt=EXTRACTION_PROMPT,
            user_message=f"Conversation to extract from:\n\n{conversation}",
            tools=EXTRACTION_TOOLS,
            max_tokens=500,
        )

        user_store.update(chat_id, result["input"])

    except Exception as e:
        print(f"[handoff] Failed for thread {old_thread_id}: {e}")
