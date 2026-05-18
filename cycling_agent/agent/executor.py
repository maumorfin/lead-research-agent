import json
from models.plan import ResearchPlan, CyclingToolType
from tools.cycling_pcs import (
    get_individual_ranking,
    get_team_ranking,
    get_rider_profile,
    get_rider_results,
    get_race_overview,
    get_stage_results,
    get_race_startlist,
)
from tools.web_search import search
from tools.web_scraper import scrape


def execute_plan(plan: ResearchPlan) -> dict[str, str]:
    findings: dict[str, str] = {}

    for step in plan.steps:
        tool = step.tool
        query = step.query.strip()
        result: object

        try:
            if tool == CyclingToolType.PCS_RANKING:
                if query.startswith("team"):
                    parts = query.split("/")
                    top_n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 20
                    result = get_team_ranking(top_n)
                else:
                    top_n = int(query) if query.isdigit() else 20
                    result = get_individual_ranking(top_n)
                findings[step.description] = json.dumps(result, indent=2)

            elif tool == CyclingToolType.PCS_RIDER:
                result = get_rider_profile(query)
                findings[step.description] = json.dumps(result, indent=2)

            elif tool == CyclingToolType.PCS_RACE:
                parts = query.split("/")
                race_slug = parts[0]
                year = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2025
                result = get_race_overview(race_slug, year)
                findings[step.description] = json.dumps(result, indent=2)

            elif tool == CyclingToolType.PCS_STAGE:
                parts = query.split("/")
                race_slug = parts[0]
                year = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2025
                stage_num = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
                result = get_stage_results(race_slug, year, stage_num)
                findings[step.description] = json.dumps(result, indent=2)

            elif tool == CyclingToolType.PCS_STARTLIST:
                parts = query.split("/")
                race_slug = parts[0]
                year = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2025
                result = get_race_startlist(race_slug, year)
                findings[step.description] = json.dumps(result, indent=2)

            elif tool == CyclingToolType.PCS_RIDER_RESULTS:
                parts = query.split("/")
                rider_slug = parts[0]
                year = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
                result = get_rider_results(rider_slug, year)
                findings[step.description] = json.dumps(result, indent=2)

            elif tool == CyclingToolType.SEARCH:
                results = search(query)
                findings[step.description] = "\n\n".join(
                    f"[{r.title}]({r.url})\n{r.content}" for r in results
                )

            elif tool == CyclingToolType.SCRAPE:
                findings[step.description] = scrape(query)

        except Exception as e:
            findings[step.description] = f"[step failed: {e}]"

    return findings
