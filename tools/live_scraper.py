import os
import re
from firecrawl import V1FirecrawlApp
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

LIVE_SOURCES = {
    "pcs_live": "https://www.procyclingstats.com/race/{race_slug}/{year}/live",
    "pcs_stage": "https://www.procyclingstats.com/race/{race_slug}/{year}/stage-{stage}",
    "pcs_stage_live": "https://www.procyclingstats.com/race/{race_slug}/{year}/stage-{stage}/live",
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


def scrape_pcs_stage_live(race_slug: str, year: int, stage_num: int) -> str:
    url = LIVE_SOURCES["pcs_stage_live"].format(race_slug=race_slug, year=year, stage=stage_num)
    return scrape_live_page(url)


def scrape_pcs_ranking() -> str:
    return scrape_live_page(LIVE_SOURCES["pcs_ranking"])


def get_race_situation(race_slug: str, year: int, stage: int) -> str:
    """
    Scrape the live Situation box from PCS using Playwright.
    Returns current groups, time gaps, riders, and race stats.
    Falls back to Firecrawl if Playwright fails.
    """
    url = f"https://www.procyclingstats.com/race/{race_slug}/{year}/stage-{stage}/live"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(5000)

            output = []

            # Race stats bar (KM to go, race time, avg speed)
            try:
                stats_selectors = {
                    "KM to go": ".kttogo, [class*='kmtogo'], .km-to-go",
                    "Race time": ".racetime, [class*='racetime']",
                    "KM done": ".kmdone, [class*='kmdone']",
                    "Avg speed": ".avg, [class*='avg']",
                }
                stats_parts = []
                for label, selector in stats_selectors.items():
                    try:
                        val = page.locator(selector).first.inner_text(timeout=2000).strip()
                        if val:
                            stats_parts.append(f"{label}: {val}")
                    except Exception:
                        pass
                if not stats_parts:
                    try:
                        stats_bar = page.locator(".racestats, .livestats, [class*='stats']").first
                        text = stats_bar.inner_text(timeout=2000).strip()
                        if text:
                            stats_parts.append(text)
                    except Exception:
                        pass
                if stats_parts:
                    output.append("**Race stats:**\n" + " | ".join(stats_parts))
            except Exception:
                pass

            # Situation box (groups, time gaps, riders)
            try:
                situation_selectors = [".situation", "[class*='situation']", ".live-situation", "#situation"]
                situation_text = None
                for selector in situation_selectors:
                    try:
                        el = page.locator(selector).first
                        el.wait_for(timeout=3000)
                        situation_text = el.inner_text(timeout=3000).strip()
                        if situation_text:
                            break
                    except Exception:
                        continue

                if situation_text:
                    output.append("**Situation:**\n" + situation_text)
                else:
                    full_text = page.inner_text("body")
                    match = re.search(r'Situation(.{50,2000}?)(?:Break|Timeline|Menu|$)', full_text, re.DOTALL)
                    if match:
                        output.append("**Situation:**\n" + match.group(1).strip())
            except Exception as e:
                output.append(f"[Situation box not found: {e}]")

            # Timeline (last 20 lines)
            try:
                timeline_selectors = [".timeline", "[class*='timeline']", "#timeline"]
                for selector in timeline_selectors:
                    try:
                        el = page.locator(selector).first
                        timeline_text = el.inner_text(timeout=3000).strip()
                        if timeline_text:
                            lines = [ln.strip() for ln in timeline_text.split("\n") if ln.strip()]
                            output.append("**Latest timeline updates:**\n" + "\n".join(lines[:20]))
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            browser.close()
            return "\n\n".join(output) if output else "[Playwright: page loaded but no live data found]"

    except PlaywrightTimeout:
        fallback = scrape_pcs_stage_live(race_slug, year, stage)
        return f"[Playwright timed out — Firecrawl fallback]\n\n{fallback}"

    except Exception as e:
        return f"[Playwright failed: {e}]"
