"""
Calendar refresh agent — discovers active cycling races automatically.
Runs once per day. Uses Tavily + Groq + PCS validation.
Three protection layers prevent bad data from reaching the store.
"""
import httpx
import json
import logging
import re
import time
from watcher.race_store import RaceStore

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

CURRENT_YEAR  = 2026
REFRESH_HOURS = 20       # minimum hours between refreshes
MAX_STAGE     = 30       # sanity cap — no race has more stages than this
VALID_YEARS   = {2025, 2026}

# Known PCS slugs for common race name variations
SLUG_HINTS = {
    "tour de france":          "tour-de-france",
    "giro d'italia":           "giro-d-italia",
    "giro":                    "giro-d-italia",
    "vuelta":                  "vuelta-a-espana",
    "vuelta a espana":         "vuelta-a-espana",
    "paris roubaix":           "paris-roubaix",
    "liege bastogne liege":    "liege-bastogne-liege",
    "il lombardia":            "il-lombardia",
    "tour of flanders":        "ronde-van-vlaanderen",
    "milan san remo":          "milano-sanremo",
    "strade bianche":          "strade-bianche",
    "criterium du dauphine":   "criterium-du-dauphine",
    "tirreno adriatico":       "tirreno-adriatico",
    "paris nice":              "paris-nice",
    "dauphine":                "criterium-du-dauphine",
}

# ── Extraction tool ───────────────────────────────────────────────────────────

EXTRACTION_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "submit_race_calendar",
            "description": "Submit the extracted list of active cycling races",
            "parameters": {
                "type": "object",
                "properties": {
                    "races": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Official race name e.g. Giro d'Italia",
                                },
                                "slug": {
                                    "type": "string",
                                    "description": "PCS URL slug e.g. giro-d-italia",
                                },
                                "year": {
                                    "type": "integer",
                                    "description": "Race year e.g. 2026",
                                },
                                "current_stage": {
                                    "type": "integer",
                                    "description": "Current or most recent stage number",
                                },
                                "total_stages": {
                                    "type": "integer",
                                    "description": "Total number of stages in the race",
                                },
                                "is_live": {
                                    "type": "boolean",
                                    "description": "True if a stage is racing today",
                                },
                            },
                            "required": [
                                "name", "slug", "year",
                                "current_stage", "total_stages", "is_live",
                            ],
                        },
                    }
                },
                "required": ["races"],
            },
        },
    }
]

EXTRACTION_PROMPT = f"""You are a professional cycling calendar assistant.
Extract all professional cycling races currently happening or recently finished
from the search results provided.

For each race extract:
- Official name
- PCS slug (procyclingstats.com URL format, lowercase with hyphens)
- Year ({CURRENT_YEAR})
- Current stage number (or most recent completed stage)
- Total stages in the race
- Whether a stage is racing TODAY (is_live: true/false)

PCS slug format rules:
- Lowercase, hyphens instead of spaces
- "Giro d'Italia" → "giro-d-italia"
- "Tour de France" → "tour-de-france"
- "Vuelta a España" → "vuelta-a-espana"
- "Paris-Roubaix" → "paris-roubaix"

Only include races you are confident about.
If unsure about a slug, make your best guess in the correct format.
Current year is {CURRENT_YEAR}."""


# ── Validation ────────────────────────────────────────────────────────────────

def _normalize_slug(raw_slug: str, race_name: str) -> str:
    """Normalize a slug from LLM output. Checks hint table first, then cleans raw slug."""
    name_lower = race_name.lower().strip()
    if name_lower in SLUG_HINTS:
        return SLUG_HINTS[name_lower]

    slug_lower = raw_slug.lower().strip()
    if slug_lower in SLUG_HINTS:
        return SLUG_HINTS[slug_lower]

    cleaned = re.sub(r"[^a-z0-9-]", "-", slug_lower)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned


def _sanity_check(race: dict) -> tuple[bool, str]:
    """Layer 1 validation — basic sanity checks on LLM output. Returns (valid, reason)."""
    slug  = race.get("slug", "")
    year  = race.get("year", 0)
    stage = race.get("current_stage", 0)
    name  = race.get("name", "")
    total = race.get("total_stages", 0)

    if not slug or len(slug) < 3:
        return False, f"Slug too short: '{slug}'"

    if year not in VALID_YEARS:
        return False, f"Invalid year: {year}"

    if not name or len(name) < 3:
        return False, f"Name too short: '{name}'"

    # current_stage=0 means Groq couldn't determine it — default to 1 (acceptable)
    if stage == 0:
        race["current_stage"] = 1
        stage = 1

    if not (1 <= stage <= MAX_STAGE):
        return False, f"Invalid stage: {stage}"

    # total_stages=0 means Groq couldn't determine it — default to 21 (grand tour assumption)
    if total == 0:
        race["total_stages"] = 21
        total = 21

    if not (1 <= total <= MAX_STAGE):
        return False, f"Invalid total stages: {total}"

    return True, "ok"


def _confirm_on_pcs(slug: str, year: int) -> bool:
    """Layer 2 validation — confirm race exists on PCS. Returns True if PCS returns 200."""
    url = f"https://www.procyclingstats.com/race/{slug}/{year}"
    try:
        response = httpx.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
            follow_redirects=True,
        )
        # 403 = access blocked but resource exists; 404 = truly not found
        valid = response.status_code in (200, 403)
        if not valid:
            logger.warning(f"[calendar] PCS returned {response.status_code} for {url}")
        return valid
    except Exception as e:
        logger.warning(f"[calendar] PCS check failed for {url}: {e}")
        return False


# ── PCS homepage scraper (primary source) ────────────────────────────────────

def _fetch_from_pcs_homepage(race_store: RaceStore) -> list[dict] | None:
    """
    Scrape the PCS homepage live stats section.
    This is the primary and most reliable source — slugs and stages come
    directly from PCS hrefs, so no Groq extraction or PCS confirmation needed.

    href format: race/{slug}/{year}/stage-{N}/live
    Returns list of race dicts, or None if the page is blocked/unavailable.
    """
    try:
        from bs4 import BeautifulSoup
        response = httpx.get(
            "https://www.procyclingstats.com/",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            timeout=10,
            follow_redirects=True,
        )

        if response.status_code != 200:
            logger.warning(f"[calendar] PCS homepage returned {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        livestats = soup.find("ul", class_="hp3-livestats")
        if not livestats:
            logger.warning("[calendar] PCS homepage: hp3-livestats section not found")
            return None

        races = []
        for li in livestats.find_all("li"):
            a = li.find("a")
            if not a:
                continue

            href = a.get("href", "").strip("/")
            text = li.get_text(strip=True)

            # href: race/{slug}/{year}/stage-{N}/live
            parts = href.split("/")
            if len(parts) < 4 or parts[0] != "race":
                continue

            slug = parts[1]
            try:
                year = int(parts[2])
            except (ValueError, IndexError):
                continue

            if year not in VALID_YEARS:
                continue

            try:
                stage = int(parts[3].replace("stage-", ""))
            except (ValueError, IndexError):
                stage = 1

            # "live..." = stage is racing now; "soon..." = starts today
            is_live = text.startswith("live")

            # Extract name: strip "live"/"soon" prefix, take everything before "|"
            name_raw = text[4:].split("|")[0].strip()  # skip 4-char prefix
            name = name_raw if len(name_raw) >= 3 else slug.replace("-", " ").title()

            # Preserve existing total_stages from store if known
            existing = race_store.get(slug)
            total_stages = existing.total_stages if existing and existing.total_stages > 1 else 21

            races.append({
                "slug":          slug,
                "name":          name,
                "year":          year,
                "current_stage": stage,
                "total_stages":  total_stages,
                "is_live":       is_live,
            })

            status = "LIVE" if is_live else "soon"
            logger.info(f"[calendar] PCS: {status}  {name}  stage {stage}  ({slug})")

        return races if races else None

    except Exception as e:
        logger.error(f"[calendar] PCS homepage scrape failed: {e}")
        return None


# ── Tavily + Groq fallback ────────────────────────────────────────────────────

def _fetch_from_tavily_groq() -> list[dict] | None:
    """
    Fallback: Tavily search + Groq extraction.
    Used when PCS homepage is blocked or returns no results.
    Costs 1 Tavily call + 1 Groq call.
    """
    try:
        from tools.web_search import search
        results = search(
            f"professional cycling race live today stage {CURRENT_YEAR}",
            max_results=8,
        )
        if not results:
            logger.warning("[calendar] Tavily returned no results")
            return None

        for i, r in enumerate(results, 1):
            logger.info(f"[calendar] Tavily result {i}: {r.url}")

        search_text = "\n\n".join(
            f"[{r.title}]\n{r.content}" for r in results
        )

    except Exception as e:
        logger.error(f"[calendar] Tavily search failed: {e}")
        return None

    try:
        from agent.llm_client import call_llm
        from config import ModelConfig

        result = call_llm(
            model_config=ModelConfig(
                provider="groq",
                model_id="llama-3.3-70b-versatile",
                display_name="Groq (calendar fallback)",
            ),
            system_prompt=EXTRACTION_PROMPT,
            user_message=f"Search results from today:\n\n{search_text}",
            tools=EXTRACTION_TOOL,
            max_tokens=1000,
        )

        races = result["input"].get("races", [])
        logger.info(f"[calendar] Groq extracted {len(races)} races (Tavily fallback)")
        return races if races else None

    except Exception as e:
        logger.error(f"[calendar] Groq extraction failed: {e}")
        return None


# ── Main refresh function ─────────────────────────────────────────────────────

async def refresh_calendar(
    race_store: RaceStore,
    force:      bool = False,
) -> int:
    """
    Discover active cycling races and update the race store.
    Primary source: PCS homepage (free, authoritative, no LLM needed).
    Fallback: Tavily search + Groq extraction (1 call each).

    Args:
        race_store: RaceStore instance to write to
        force:      Skip the cache check and always refresh

    Returns:
        Number of valid races written to the store
    """
    if not force and not race_store.needs_refresh(REFRESH_HOURS):
        logger.info("[calendar] Data still fresh — skipping refresh")
        return 0

    logger.info("[calendar] Starting calendar refresh...")

    # ── Primary: scrape PCS homepage directly ─────────────────────────────────
    races = _fetch_from_pcs_homepage(race_store)
    pcs_source = races is not None

    if not races:
        logger.warning("[calendar] PCS homepage unavailable — falling back to Tavily+Groq")
        races = _fetch_from_tavily_groq()

    if not races:
        logger.warning("[calendar] No races found from any source — keeping existing data")
        return 0

    # ── Validate and write ────────────────────────────────────────────────────
    valid_count = 0
    race_store.mark_all_not_live()

    for race in races:
        # Normalize slug only for Tavily/Groq results (PCS slugs are already correct)
        if not pcs_source:
            race["slug"] = _normalize_slug(race.get("slug", ""), race.get("name", ""))

        # Sanity check
        valid, reason = _sanity_check(race)
        if not valid:
            logger.warning(f"[calendar] Skipping {race.get('name')}: {reason}")
            continue

        # PCS confirmation only needed for Tavily/Groq results
        # (PCS homepage races are already confirmed — they came from PCS)
        if not pcs_source and not _confirm_on_pcs(race["slug"], race["year"]):
            logger.warning(f"[calendar] PCS rejected {race['slug']}/{race['year']}")
            continue

        try:
            race_store.upsert(
                slug=race["slug"],
                name=race["name"],
                year=race["year"],
                current_stage=race["current_stage"],
                is_live=race["is_live"],
                total_stages=race["total_stages"],
            )
            valid_count += 1
            logger.info(
                f"[calendar] Wrote: {race['name']} "
                f"stage {race['current_stage']} live={race['is_live']}"
            )
        except Exception as e:
            logger.error(f"[calendar] Write failed for {race.get('name')}: {e}")

    if valid_count > 0:
        race_store.set_last_refresh()
        source = "PCS homepage" if pcs_source else "Tavily+Groq fallback"
        logger.info(f"[calendar] Refresh complete — {valid_count} races written via {source}")
    else:
        logger.warning("[calendar] Zero valid races — keeping existing data")

    return valid_count
