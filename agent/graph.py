import json
import sqlite3
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from memory.user_store import UserStore
from config import get_model
from agent.llm_client import call_llm
from agent.executor import execute_plan
from models.plan import ResearchPlan
from models.answer import CyclingAnswer
from tools.cycling_pcs import COMMON_RACE_SLUGS


# --- State ---

def _append_messages(left: list, right: list) -> list:
    return left + right


class AgentState(TypedDict):
    question:          str
    resolved_question: str
    chat_id:           int
    plan:              ResearchPlan | None
    findings:          dict
    answer:            CyclingAnswer | None
    messages:          Annotated[list, _append_messages]


# --- Prompts ---

RESOLVER_PROMPT = """You are a conversation context resolver for a cycling assistant.

Your job: rewrite the user's latest question into a fully self-contained question
that can be understood without any prior context.

Rules:
- Replace ALL pronouns (he, she, they, it, his, her) with the actual name
- Replace vague references ("that race", "yesterday's stage", "the same team")
  with the actual entity from conversation history
- If the question is already self-contained, return it unchanged
- Never answer the question — only rewrite it
- Keep it concise and natural

Examples:
  History: [Q: "Who is leading the Giro?", A: "Pogačar leads by 45 seconds"]
  Question: "What did he win this year?"
  Rewritten: "What races did Tadej Pogačar win in 2026?"

  History: [Q: "Tell me about the Tour de France 2026"]
  Question: "Who won it?"
  Rewritten: "Who won the Tour de France 2026?"

  History: []
  Question: "Who leads the WorldTour?"
  Rewritten: "Who leads the WorldTour?"  (already self-contained)
"""

PLANNER_PROMPT_BASE = f"""You are a professional cycling data analyst assistant.
Given a user's question about professional cycling, create a focused research plan
to gather the data needed to answer it precisely.

Available tools:
- pcs_ranking: UCI WorldTour standings. Query: "20" for top 20, "team/20" for teams
- pcs_rider: Rider profile. Query: "tadej-pogacar"
- pcs_race: Race overview and GC. Query: "race-slug/year"
- pcs_stage: Stage results. Query: "race-slug/year/stage-number"
- pcs_startlist: Race startlist. Query: "race-slug/year"
- pcs_rider_results: Rider season results. Query: "rider-slug/year"
- search: Tavily web search for news and general information
- scrape: Static HTML page. Query: full URL
- firecrawl: JS-rendered pages.
  Query formats:
    "situation/race-slug/year/stage"  → LIVE groups, time gaps, riders (use for live questions)
    "live/race-slug/year"             → full live ticker
    "gc/race-slug/year"               → GC standings
    "stage/race-slug/year/N"          → stage page
    "ranking"                         → WorldTour ranking
    "https://..."                     → direct URL

Generate 2 to 5 steps. Current year is 2026.

Common race slugs:
{json.dumps(COMMON_RACE_SLUGS, indent=2)}
"""

SYNTHESIZER_PROMPT = """You are a passionate cycling fan and expert analyst —
like a knowledgeable friend who loves the sport and remembers what you've been talking about.

Tone:
- Conversational, warm, natural — not a formal report
- Reference the conversation naturally when relevant
  e.g. "Yeah, so after what we said about Pogačar earlier — he also won..."
  e.g. "Good follow-up — that's actually connected to the Giro situation..."
- Short sentences where possible. No bullet-point-heavy answers unless the
  user explicitly asked for a list
- If the user asked a short question, give a short answer first, then expand

Content:
- Be precise with numbers, dates, names
- Never invent facts — if data is missing say so directly
- Suggest 1-2 natural follow-up questions as if continuing a conversation
  e.g. "Want me to check how he did in the mountain stages specifically?"
- Match the user's language if known from their profile
- Set confidence honestly
- Always note where the data came from"""

SUMMARIZATION_PROMPT = """Summarize this cycling conversation into 3-5 sentences.
Keep: key facts established, riders and races discussed, questions asked and answered.
Discard: filler, repeated information, tool outputs.
Write it as context for the next conversation, not as a transcript."""

# Flat schemas for cross-provider compatibility
_RESOLVER_SCHEMA = {
    "type": "object",
    "properties": {
        "resolved_question": {
            "type": "string",
            "description": "The fully self-contained rewritten question",
        },
        "entities_referenced": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Riders/races/teams that were resolved e.g. tadej-pogacar, giro-d-italia",
        },
    },
    "required": ["resolved_question", "entities_referenced"],
}

_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "The original user question"},
        "steps": {
            "type": "array",
            "description": "2 to 5 targeted research steps",
            "items": {
                "type": "object",
                "properties": {
                    "step_id":     {"type": "integer"},
                    "description": {"type": "string", "description": "What this step is trying to find out"},
                    "tool": {
                        "type": "string",
                        "enum": ["pcs_ranking", "pcs_rider", "pcs_race", "pcs_stage",
                                 "pcs_startlist", "pcs_rider_results", "search", "scrape", "firecrawl"],
                    },
                    "query": {"type": "string", "description": "Slug, URL, or search string"},
                },
                "required": ["step_id", "description", "tool", "query"],
            },
        },
    },
    "required": ["question", "steps"],
}

_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "question":             {"type": "string"},
        "answer":               {"type": "string", "description": "Main answer in clear prose, 3-6 sentences"},
        "data_points":          {"type": "array", "items": {"type": "string"}, "description": "Key facts as bullet points"},
        "source_note":          {"type": "string", "description": "Where the data came from"},
        "follow_up_suggestions": {"type": "array", "items": {"type": "string"}, "description": "1-2 natural follow-up questions"},
        "confidence":           {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["question", "answer", "data_points", "follow_up_suggestions", "confidence"],
}

RESOLVER_TOOLS = [{"type": "function", "function": {
    "name": "submit_resolved_question",
    "description": "Submit the rewritten self-contained question",
    "parameters": _RESOLVER_SCHEMA,
}}]

PLANNER_TOOLS = [{"type": "function", "function": {
    "name": "submit_research_plan",
    "description": "Submit the structured research plan for execution",
    "parameters": _PLAN_SCHEMA,
}}]

SYNTHESIZER_TOOLS = [{"type": "function", "function": {
    "name": "submit_cycling_answer",
    "description": "Submit the final structured cycling answer",
    "parameters": _ANSWER_SCHEMA,
}}]

SUMMARY_TOOLS = [{"type": "function", "function": {
    "name": "submit_summary",
    "description": "Submit the conversation summary",
    "parameters": {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
    },
}}]

SUMMARY_THRESHOLD = 20


# --- Nodes ---

def summarization_node(state: AgentState, *, user_store: UserStore) -> dict:
    messages = state.get("messages", [])
    if len(messages) < SUMMARY_THRESHOLD:
        return {}

    to_summarize = messages[:-6]
    recent       = messages[-6:]

    conversation = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in to_summarize
        if isinstance(m, dict)
    )

    try:
        summary_text = call_llm(
            model_config=get_model(state["chat_id"]),
            system_prompt=SUMMARIZATION_PROMPT,
            user_message=conversation,
            tools=SUMMARY_TOOLS,
            max_tokens=500,
        )["input"]["summary"]
    except Exception:
        return {}

    compressed = [
        {"role": "system", "content": f"[Conversation summary]: {summary_text}"},
        *recent,
    ]
    return {"messages": compressed}


def resolver_node(state: AgentState) -> dict:
    messages = state.get("messages", [])

    if len(messages) < 2:
        return {"resolved_question": state["question"]}

    recent = messages[-6:]
    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in recent
        if isinstance(m, dict) and m.get("content")
    )

    try:
        result = call_llm(
            model_config=get_model(state["chat_id"]),
            system_prompt=RESOLVER_PROMPT,
            user_message=(
                f"Conversation history:\n{history_text}\n\n"
                f"Latest question to resolve: {state['question']}"
            ),
            tools=RESOLVER_TOOLS,
            max_tokens=300,
        )
        return {"resolved_question": result["input"]["resolved_question"]}
    except Exception:
        return {"resolved_question": state["question"]}


def planner_node(state: AgentState, *, user_store: UserStore) -> dict:
    user_context = user_store.format_for_prompt(state["chat_id"])
    system_prompt = PLANNER_PROMPT_BASE
    if user_context:
        system_prompt += f"\n\n{user_context}"

    question_to_plan = state.get("resolved_question") or state["question"]

    result = call_llm(
        model_config=get_model(state["chat_id"]),
        system_prompt=system_prompt,
        user_message=question_to_plan,
        tools=PLANNER_TOOLS,
        max_tokens=2000,
    )
    return {"plan": ResearchPlan(**result["input"])}


def executor_node(state: AgentState) -> dict:
    findings = execute_plan(state["plan"])
    return {"findings": findings}


def _repair_answer(data: dict) -> dict:
    """Coerce Groq's occasionally malformed answer fields into the expected types.

    Groq sometimes fills array fields with CDATA-wrapped strings or omits
    required fields entirely. This repairs the dict before Pydantic sees it.
    """
    import re

    def to_list(val):
        if isinstance(val, list):
            return val
        if not isinstance(val, str):
            return []
        val = re.sub(r"<!\[CDATA\[|\]\]>", "", val)
        lines = [re.sub(r"^[-•*\d.]+\s*", "", ln).strip() for ln in val.splitlines()]
        return [ln for ln in lines if ln]

    out = dict(data)
    for field in ("data_points", "follow_up_suggestions"):
        if not isinstance(out.get(field), list):
            out[field] = to_list(out.get(field, []))
    if "confidence" not in out or out["confidence"] not in ("high", "medium", "low"):
        out["confidence"] = "medium"
    out.setdefault("source_note", None)
    return out


def synthesizer_node(state: AgentState, *, user_store: UserStore) -> dict:
    findings_text = "\n\n---\n\n".join(
        f"**{topic}**\n{content}"
        for topic, content in state["findings"].items()
    )

    messages = state.get("messages", [])
    recent   = messages[-4:] if len(messages) >= 4 else messages

    history_context = ""
    if recent:
        history_context = "\n\nRecent conversation:\n" + "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in recent
            if isinstance(m, dict) and m.get("content")
        )

    original  = state["question"]
    resolved  = state.get("resolved_question", original)
    q_context = f"Original question: {original}"
    if resolved != original:
        q_context += f"\nResolved to: {resolved}"

    result = call_llm(
        model_config=get_model(state["chat_id"]),
        system_prompt=SYNTHESIZER_PROMPT,
        user_message=(
            f"{q_context}"
            f"{history_context}\n\n"
            f"Research findings:\n\n{findings_text}"
        ),
        tools=SYNTHESIZER_TOOLS,
        max_tokens=3000,
    )
    try:
        answer = CyclingAnswer(**result["input"])
    except Exception:
        answer = CyclingAnswer(**_repair_answer(result["input"]))

    new_messages = [
        {"role": "user",      "content": original},
        {"role": "assistant", "content": answer.answer},
    ]
    return {"answer": answer, "messages": new_messages}


# --- Graph builder ---

def build_graph(db_path: str = "data/checkpoints.db"):
    import os
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    user_store   = UserStore()
    conn         = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn).with_allowlist(["models.plan", "models.answer"])

    def _summarization(state): return summarization_node(state, user_store=user_store)
    def _resolver(state):      return resolver_node(state)
    def _planner(state):       return planner_node(state, user_store=user_store)
    def _synthesizer(state):   return synthesizer_node(state, user_store=user_store)

    graph = StateGraph(AgentState)
    graph.add_node("summarizer",  _summarization)
    graph.add_node("resolver",    _resolver)
    graph.add_node("planner",     _planner)
    graph.add_node("executor",    executor_node)
    graph.add_node("synthesizer", _synthesizer)

    graph.set_entry_point("summarizer")
    graph.add_edge("summarizer",  "resolver")
    graph.add_edge("resolver",    "planner")
    graph.add_edge("planner",     "executor")
    graph.add_edge("executor",    "synthesizer")
    graph.add_edge("synthesizer", END)

    app = graph.compile(checkpointer=checkpointer)
    return app, user_store
