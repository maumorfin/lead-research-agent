"""
Groq event judge — the only LLM call in the proactive watcher.
Called only when the rule engine passes a diff (roughly 10% of polls).

Decision: is this diff worth interrupting the user for?
Output:   yes/no + a short Telegram-ready message if yes.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class JudgeResult:
    should_notify: bool
    message:       str        # Telegram-ready message, empty if should_notify=False
    reason:        str        # why the judge decided this way (for logging)
    confidence:    str        # "high", "medium", "low"


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a live cycling race assistant deciding whether to
send a push notification to a cycling fan.

Your job: read a race update diff and decide if it is worth interrupting
the user. Be selective — only notify for genuinely exciting or important moments.

NOTIFY for:
- Attacks and accelerations by GC contenders
- Crashes or abandonments
- Stage wins and podium finishes
- Significant time gap changes (>30 seconds opening or closing)
- A rider the user follows making a move
- Final km situations (inside 10km with action happening)

DO NOT notify for:
- Routine peloton updates with no drama
- km markers with no event
- Classification updates mid-race with no change
- Anything that could wait until the stage ends

When you notify, write a SHORT Telegram message (2-3 sentences max).
Tone: excited but factual. Like a knowledgeable friend texting you.
Use the rider's real name, not their slug format.
Include the time gap or km to go if known from the diff.

Respond ONLY with valid JSON. No markdown, no explanation outside the JSON."""

JUDGE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_judgment",
            "description": "Submit the notification decision",
            "parameters": {
                "type": "object",
                "properties": {
                    "should_notify": {
                        "type": "boolean",
                        "description": "True if this update is worth sending to the user"
                    },
                    "message": {
                        "type": "string",
                        "description": "The Telegram message to send. Empty string if should_notify=False. 2-3 sentences max, no HTML tags."
                    },
                    "reason": {
                        "type": "string",
                        "description": "One sentence explaining the decision (for logging only, not shown to user)"
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "How confident the judge is in this decision"
                    },
                },
                "required": ["should_notify", "message", "reason", "confidence"],
            },
        },
    }
]


# ── Core judge function ───────────────────────────────────────────────────────

def judge_event(
    diff:         str,
    race_slug:    str,
    year:         int,
    stage:        int,
    user_profile: dict | None = None,
    chat_id:      int = 0,
) -> JudgeResult:
    """
    Ask Groq whether this diff is worth notifying the user about.

    Always uses Groq regardless of the user's /model setting —
    the judge is infrastructure, not a user-facing feature.

    Returns JudgeResult with should_notify=False on any error
    so failures are always safe (no spurious notifications).
    """
    try:
        from agent.llm_client import call_llm
        from config import AVAILABLE_MODELS

        race_name    = race_slug.replace("-", " ").title()
        user_context = _format_user_context(user_profile)

        user_message = f"""Race: {race_name} {year} — Stage {stage}
{user_context}
Latest update from live ticker:
{diff}

Should I notify this user?"""

        result_raw = call_llm(
            model_config=AVAILABLE_MODELS["haiku"],
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            tools=JUDGE_TOOLS,
            max_tokens=300,
        )

        data = result_raw["input"]

        result = JudgeResult(
            should_notify=data["should_notify"],
            message=data.get("message", ""),
            reason=data.get("reason", ""),
            confidence=data.get("confidence", "low"),
        )

        logger.info(
            f"[judge] chat={chat_id} notify={result.should_notify} "
            f"confidence={result.confidence} reason={result.reason}"
        )

        return result

    except Exception as e:
        logger.error(f"[judge] Failed for chat {chat_id}: {e}")
        return JudgeResult(
            should_notify=False,
            message="",
            reason=f"Judge failed: {e}",
            confidence="low",
        )


def judge_event_for_users(
    diff:          str,
    race_slug:     str,
    year:          int,
    stage:         int,
    user_profiles: dict[int, dict],
) -> dict[int, JudgeResult]:
    """
    Run the judge for multiple users efficiently.

    Strategy: run one shared judgment for the event itself,
    then personalize the message per user if they have a
    specific rider mentioned in the diff.

    This avoids N separate Groq calls for N users watching
    the same race — one call, personalized output.
    """
    if not user_profiles:
        return {}

    first_chat_id = next(iter(user_profiles))
    base_result   = judge_event(
        diff=diff,
        race_slug=race_slug,
        year=year,
        stage=stage,
        user_profile=user_profiles[first_chat_id],
        chat_id=first_chat_id,
    )

    if not base_result.should_notify:
        return {}

    return {
        chat_id: JudgeResult(
            should_notify=True,
            message=base_result.message,
            reason=base_result.reason,
            confidence=base_result.confidence,
        )
        for chat_id in user_profiles
    }


def _format_user_context(user_profile: dict | None) -> str:
    """Format user profile into a compact context string for the prompt."""
    if not user_profile:
        return "User profile: no preferences recorded yet."

    parts = []

    riders = user_profile.get("riders_mentioned", [])
    if riders:
        names = [r.replace("-", " ").title() for r in riders[:5]]
        parts.append(f"Riders they follow: {', '.join(names)}")

    races = user_profile.get("races_followed", [])
    if races:
        names = [r.replace("-", " ").title() for r in races[:3]]
        parts.append(f"Races they follow: {', '.join(names)}")

    lang = user_profile.get("language", "en")
    if lang != "en":
        parts.append(f"Preferred language: {lang} — write the message in this language")

    if not parts:
        return "User profile: no specific preferences recorded."

    return "User profile:\n" + "\n".join(f"- {p}" for p in parts)
