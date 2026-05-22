import sys
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

sys.path.insert(0, os.path.dirname(__file__))
load_dotenv()

from agent.graph import build_graph
from memory.session_manager import SessionManager

console = Console()
app, user_store = build_graph()
session_mgr = SessionManager()


def run_agent(question: str, chat_id: int = 0):
    console.print(
        Panel(f"[bold]{question}[/bold]", title="[blue]Pro Cycling Intelligence Agent[/blue]", border_style="blue")
    )

    session = session_mgr.get_or_create(chat_id)

    if session.is_new and session.old_thread_id:
        from memory.handoff import run_handoff
        console.print("[dim]Running session handoff...[/dim]")
        run_handoff(session.old_thread_id, chat_id, app, user_store)

    result = app.invoke(
        {
            "question": question,
            "chat_id":  chat_id,
            "messages": [],
            "findings": {},
            "plan":     None,
            "answer":   None,
        },
        config={"configurable": {"thread_id": session.thread_id}},
    )

    answer = result["answer"]
    color  = "green" if answer.confidence == "high" else "yellow" if answer.confidence == "medium" else "red"

    console.print(
        Panel(answer.answer, title=f"[{color}]Answer — {answer.confidence}[/{color}]", border_style=color)
    )

    if answer.data_points:
        console.print("\n[bold]Key Facts:[/bold]")
        for p in answer.data_points:
            console.print(f"  • {p}")

    if answer.follow_up_suggestions:
        console.print("\n[bold]You might also ask:[/bold]")
        for i, s in enumerate(answer.follow_up_suggestions, 1):
            console.print(f"  {i}. {s}")

    if answer.source_note:
        console.print(f"\n[dim italic]{answer.source_note}[/dim italic]")

    console.print()
    return answer


def main():
    if len(sys.argv) < 2:
        console.print(Panel(
            "Usage: [bold]python main.py \"Your cycling question\"[/bold]\n\n"
            "Examples:\n"
            "  python main.py \"Who is leading the WorldTour right now?\"\n"
            "  python main.py \"Show me Pogacar's results in 2026\"\n"
            "  python main.py \"What happened in stage 5 of the Giro 2026?\"",
            title="Pro Cycling Intelligence Agent",
            border_style="blue",
        ))
        sys.exit(0)

    question = " ".join(sys.argv[1:])
    run_agent(question, chat_id=0)


if __name__ == "__main__":
    main()
