import sys
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

sys.path.insert(0, os.path.dirname(__file__))
load_dotenv()

from agent.planner import create_plan
from agent.executor import execute_plan
from agent.synthesizer import synthesize
from models.plan import CyclingToolType

console = Console()


def run_agent(question: str):
    console.print(
        Panel(
            f"[bold]{question}[/bold]",
            title="[blue]Pro Cycling Intelligence Agent[/blue]",
            border_style="blue",
        )
    )

    console.print("\n[cyan]Planning research...[/cyan]")
    plan = create_plan(question, chat_id=0)
    console.print(f"[cyan]{len(plan.steps)} steps planned:[/cyan]")
    for step in plan.steps:
        console.print(f"  [{step.tool.value}] {step.description}")

    console.print("\n[yellow]Executing steps...[/yellow]")
    findings = execute_plan(plan)

    console.print("[green]Synthesizing answer...[/green]\n")
    answer = synthesize(question, findings, chat_id=0)

    color = "green" if answer.confidence == "high" else "yellow" if answer.confidence == "medium" else "red"
    console.print(
        Panel(
            answer.answer,
            title=f"[{color}]Answer — confidence: {answer.confidence}[/{color}]",
            border_style=color,
        )
    )

    if answer.data_points:
        console.print("\n[bold]Key Facts:[/bold]")
        for point in answer.data_points:
            console.print(f"  • {point}")

    if answer.follow_up_suggestions:
        console.print("\n[bold]You might also ask:[/bold]")
        for i, s in enumerate(answer.follow_up_suggestions, 1):
            console.print(f"  {i}. {s}")

    if answer.source_note:
        console.print(f"\n[dim italic]{answer.source_note}[/dim italic]")

    console.print()


def main():
    if len(sys.argv) < 2:
        console.print(Panel(
            "Usage: [bold]python main.py \"Your cycling question\"[/bold]\n\n"
            "Examples:\n"
            "  python main.py \"Who is leading the WorldTour right now?\"\n"
            "  python main.py \"Show me Pogacar's results in 2025\"\n"
            "  python main.py \"What happened in stage 5 of the Giro 2025?\"",
            title="Pro Cycling Intelligence Agent",
            border_style="blue",
        ))
        sys.exit(0)

    question = " ".join(sys.argv[1:])
    run_agent(question)


if __name__ == "__main__":
    main()
