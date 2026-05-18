from models.plan import ResearchPlan, ToolType
from tools.web_search import search
from tools.web_scraper import scrape


def execute_plan(plan: ResearchPlan) -> dict[str, str]:
    findings: dict[str, str] = {}

    for step in plan.steps:
        if step.tool == ToolType.SEARCH:
            results = search(step.query)
            combined = "\n\n".join(
                f"[{r.title}]({r.url})\n{r.content}" for r in results
            )
            findings[step.description] = combined

        elif step.tool == ToolType.SCRAPE:
            content = scrape(step.query)
            findings[step.description] = content

    return findings
