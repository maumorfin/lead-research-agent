import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from agent.planner import create_plan
from agent.executor import execute_plan
from agent.synthesizer import synthesize
from models.lead import LeadProfile

load_dotenv()
console = Console()

SAMPLE_COMPANIES = ["Stripe", "Linear", "Vercel"]


def research_company(company_name: str) -> LeadProfile:
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Planning research for {company_name}...", total=None
        )
        plan = create_plan(company_name)

        progress.update(
            task,
            description=f"[yellow]Executing {len(plan.steps)} research steps for {company_name}...",
        )
        findings = execute_plan(plan)

        progress.update(task, description=f"[green]Synthesizing profile for {company_name}...")
        profile = synthesize(company_name, findings)

    return profile


def display_profile(profile: LeadProfile) -> None:
    score = profile.qualification_score
    color = "green" if score >= 7 else "yellow" if score >= 4 else "red"

    console.print(
        Panel(
            f"[bold]{profile.company_name}[/bold]\n"
            f"[dim]{profile.description or 'No description found'}[/dim]\n\n"
            f"Industry: {profile.industry or '—'} | "
            f"Size: {profile.employee_count_estimate or '—'} | "
            f"Founded: {profile.founding_year or '—'}\n"
            f"HQ: {profile.headquarters or '—'} | "
            f"Website: {profile.website or '—'}\n"
            f"Funding: {profile.funding_info or '—'} | "
            f"Hiring: {'Yes' if profile.is_hiring else 'No' if profile.is_hiring is False else '—'}",
            title=f"[{color}]Score: {score}/10[/{color}]",
            border_style=color,
        )
    )

    if profile.key_people:
        console.print("[bold]Key People:[/bold]")
        for person in profile.key_people:
            console.print(f"  • {person.name} — {person.title}")

    if profile.tech_stack:
        console.print(f"\n[bold]Tech Stack:[/bold] {', '.join(profile.tech_stack)}")

    if profile.talking_points:
        console.print("\n[bold]Talking Points:[/bold]")
        for point in profile.talking_points:
            console.print(f"  → {point}")

    if profile.recent_news:
        console.print("\n[bold]Recent News:[/bold]")
        for news in profile.recent_news[:3]:
            console.print(f"  • {news}")

    console.print(
        f"\n[dim italic]Reasoning: {profile.qualification_reasoning}[/dim italic]"
    )
    console.print()


def print_summary_table(profiles: list[LeadProfile]) -> None:
    table = Table(title="Lead Summary", show_header=True, header_style="bold blue")
    table.add_column("Company", style="bold")
    table.add_column("Industry")
    table.add_column("Size")
    table.add_column("Score", justify="center")
    table.add_column("Verdict", justify="center")

    for p in sorted(profiles, key=lambda x: x.qualification_score, reverse=True):
        score = p.qualification_score
        color = "green" if score >= 7 else "yellow" if score >= 4 else "red"
        verdict = "✓ Pursue" if score >= 7 else "~ Maybe" if score >= 4 else "✗ Pass"
        table.add_row(
            p.company_name,
            p.industry or "—",
            p.employee_count_estimate or "—",
            f"[{color}]{score}[/{color}]",
            f"[{color}]{verdict}[/{color}]",
        )

    console.print(table)


def main() -> None:
    companies = sys.argv[1:] if len(sys.argv) > 1 else SAMPLE_COMPANIES

    console.print(
        Panel(
            f"Researching [bold]{len(companies)}[/bold] "
            f"{'company' if len(companies) == 1 else 'companies'}: "
            f"{', '.join(companies)}",
            title="[bold blue]Lead Research Agent[/bold blue]",
            border_style="blue",
        )
    )
    console.print()

    profiles: list[LeadProfile] = []
    for company in companies:
        console.rule(f"[bold]{company}[/bold]")
        profile = research_company(company)
        display_profile(profile)
        profiles.append(profile)

    console.rule("[bold blue]Summary[/bold blue]")
    print_summary_table(profiles)


if __name__ == "__main__":
    main()
