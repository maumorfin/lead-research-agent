import os
from firecrawl import V1FirecrawlApp

LIVE_SOURCES = {
    "pcs_live": "https://www.procyclingstats.com/race/{race_slug}/{year}/live",
    "pcs_stage": "https://www.procyclingstats.com/race/{race_slug}/{year}/stage-{stage}",
    "pcs_gc": "https://www.procyclingstats.com/race/{race_slug}/{year}/gc",
    "pcs_ranking": "https://www.procyclingstats.com/rankings/me/individual",
    "eurosport": "https://www.eurosport.com/cycling/",
    "cyclingnews": "https://www.cyclingnews.com/news/",
}


def scrape_live_page(url: str, max_chars: int = 6000) -> str:
    try:
        app = V1FirecrawlApp(api_key=os.environ["FIRECRAWL_API_KEY"])
        result = app.scrape_url(url, formats=["markdown"])
        content = result.markdown or ""
        if not content:
            return "[No content returned]"
        # PCS pages have heavy navigation before the actual table.
        # Jump to the first markdown table separator to skip the nav preamble.
        table_sep = content.find("| --- |")
        if table_sep > 0:
            # Step back one line to include the column header row
            start = content.rfind("\n", 0, table_sep)
            start = content.rfind("\n", 0, start) if start > 0 else 0
            content = content[start:].lstrip()
        return content[:max_chars]
    except Exception as e:
        return f"[Firecrawl failed: {e}]"


def scrape_pcs_live(race_slug: str, year: int) -> str:
    url = LIVE_SOURCES["pcs_live"].format(race_slug=race_slug, year=year)
    return scrape_live_page(url)


def scrape_pcs_stage(race_slug: str, year: int, stage_num: int) -> str:
    url = LIVE_SOURCES["pcs_stage"].format(race_slug=race_slug, year=year, stage=stage_num)
    return scrape_live_page(url)


def scrape_pcs_gc(race_slug: str, year: int) -> str:
    url = LIVE_SOURCES["pcs_gc"].format(race_slug=race_slug, year=year)
    return scrape_live_page(url)


def scrape_pcs_ranking() -> str:
    return scrape_live_page(LIVE_SOURCES["pcs_ranking"])
