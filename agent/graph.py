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
    question: str
    chat_id:  int
    plan:     ResearchPlan | None
    findings: dict
    answer:   CyclingAnswer | None
    messages: Annotated[list, _append_messages]


# --- Prompts ---

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

SYNTHESIZER_PROMPT = """You are a knowledgeable professional cycling commentator and analyst.
Synthesize the raw research findings into a clear, accurate, engaging answer.

Guidelines:
- Be precise with numbers, dates, and rider names
- Use proper cycling terminology naturally (GC, peloton, domestique, jersey, etc.)
- Never invent facts — if data is missing say so clearly
- Suggest 2-3 relevant follow-up questions
- Match the user's language if known from their profile
- Set confidence to "high" only when data is complete and structured
- Always fill source_note"""

SUMMARIZATION_PROMPT = """Summarize this cycling conversation into 3-5 sentences.
Keep: key facts established, riders and races discussed, questions asked and answered.
Discard: filler, repeated information, tool outputs.
Write it as context for the next conversation, not as a transcript."""

# Flat schemas for cross-provider compatibility
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
        "follow_up_suggestions": {"type": "array", "items": {"type": "string"}, "description": "2-3 follow-up questions"},
        "confidence":           {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["question", "answer", "data_points", "follow_up_suggestions", "confidence"],
}

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


def planner_node(state: AgentState, *, user_store: UserStore) -> dict:
    user_context = user_store.format_for_prompt(state["chat_id"])
    system_prompt = PLANNER_PROMPT_BASE
    if user_context:
        system_prompt += f"\n\n{user_context}"

    result = call_llm(
        model_config=get_model(state["chat_id"]),
        system_prompt=system_prompt,
        user_message=state["question"],
        tools=PLANNER_TOOLS,
        max_tokens=2000,
    )
    return {"plan": ResearchPlan(**result["input"])}


def executor_node(state: AgentState) -> dict:
    findings = execute_plan(state["plan"])
    return {"findings": findings}


def synthesizer_node(state: AgentState, *, user_store: UserStore) -> dict:
    findings_text = "\n\n---\n\n".join(
        f"**{topic}**\n{content}"
        for topic, content in state["findings"].items()
    )

    result = call_llm(
        model_config=get_model(state["chat_id"]),
        system_prompt=SYNTHESIZER_PROMPT,
        user_message=f"Question: {state['question']}\n\nFindings:\n\n{findings_text}",
        tools=SYNTHESIZER_TOOLS,
        max_tokens=3000,
    )
    answer = CyclingAnswer(**result["input"])

    new_messages = [
        {"role": "user",      "content": state["question"]},
        {"role": "assistant", "content": answer.answer},
    ]
    return {"answer": answer, "messages": new_messages}


# --- Graph builder ---

def build_graph(db_path: str = "data/checkpoints.db"):
    """
    Builds and compiles the LangGraph StateGraph.
    Returns (app, user_store).
    """
    import os
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    user_store   = UserStore()
    conn         = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn).with_allowlist(["models.plan", "models.answer"])

    def _summarization(state):
        return summarization_node(state, user_store=user_store)

    def _planner(state):
        return planner_node(state, user_store=user_store)

    def _synthesizer(state):
        return synthesizer_node(state, user_store=user_store)

    graph = StateGraph(AgentState)
    graph.add_node("summarizer",  _summarization)
    graph.add_node("planner",     _planner)
    graph.add_node("executor",    executor_node)
    graph.add_node("synthesizer", _synthesizer)

    graph.set_entry_point("summarizer")
    graph.add_edge("summarizer",  "planner")
    graph.add_edge("planner",     "executor")
    graph.add_edge("executor",    "synthesizer")
    graph.add_edge("synthesizer", END)

    app = graph.compile(checkpointer=checkpointer)
    return app, user_store
