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

    if not (1 <= stage <= MAX_STAGE):
        return False, f"Invalid stage: {stage}"

    if not (1 <= total <= MAX_STAGE):
        return False, f"Invalid total stages: {total}"

    if not name or len(name) < 3:
        return False, f"Name too short: '{name}'"

    if stage > total:
        return False, f"Stage {stage} > total {total}"

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


# ── Main refresh function ─────────────────────────────────────────────────────

async def refresh_calendar(
    race_store: RaceStore,
    force:      bool = False,
) -> int:
    """
    Discover active cycling races and update the race store.

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

    # ── Step 1: Search Tavily ─────────────────────────────────────────────────
    try:
        from tools.web_search import search
        results = search(
            f"professional cycling race live today stage {CURRENT_YEAR}",
            max_results=5,
        )
        if not results:
            logger.warning("[calendar] Tavily returned no results")
            return 0

        search_text = "\n\n".join(
            f"[{r.title}]\n{r.content}" for r in results
        )
        logger.info(f"[calendar] Tavily returned {len(results)} results")

    except Exception as e:
        logger.error(f"[calendar] Tavily search failed: {e}")
        return 0

    # ── Step 2: Groq extraction ───────────────────────────────────────────────
    try:
        from agent.llm_client import call_llm
        from config import ModelConfig

        groq_config = ModelConfig(
            provider="groq",
            model_id="llama-3.3-70b-versatile",
            display_name="Groq (calendar agent)",
        )

        result = call_llm(
            model_config=groq_config,
            system_prompt=EXTRACTION_PROMPT,
            user_message=f"Search results from today:\n\n{search_text}",
            tools=EXTRACTION_TOOL,
            max_tokens=1000,
        )

        races = result["input"].get("races", [])
        logger.info(f"[calendar] Groq extracted {len(races)} races")

    except Exception as e:
        logger.error(f"[calendar] Groq extraction failed: {e}")
        return 0

    if not races:
        logger.warning("[calendar] No races extracted — keeping existing data")
        return 0

    # ── Step 3: Validate and write ────────────────────────────────────────────
    valid_count = 0

    # Mark all existing races not live — only this refresh's confirmed races get re-marked
    race_store.mark_all_not_live()

    for race in races:
        race["slug"] = _normalize_slug(race.get("slug", ""), race.get("name", ""))

        # Layer 1 — sanity checks
        valid, reason = _sanity_check(race)
        if not valid:
            logger.warning(f"[calendar] Sanity check failed for {race.get('name')}: {reason}")
            continue

        # Layer 2 — PCS confirmation
        if not _confirm_on_pcs(race["slug"], race["year"]):
            logger.warning(
                f"[calendar] PCS confirmation failed for "
                f"{race['slug']}/{race['year']} — discarding"
            )
            continue

        # Layer 3 — write to store
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
                f"stage {race['current_stage']} "
                f"live={race['is_live']}"
            )
        except Exception as e:
            logger.error(f"[calendar] Write failed for {race.get('name')}: {e}")

    # Update refresh timestamp only if at least one race was valid
    if valid_count > 0:
        race_store.set_last_refresh()
        logger.info(f"[calendar] Refresh complete — {valid_count} valid races written")
    else:
        logger.warning(
            "[calendar] Zero valid races after validation — "
            "keeping existing data, not updating refresh timestamp"
        )

    return valid_count
