import asyncio
import hashlib
import httpx
import logging
import re
from dataclasses import dataclass
from datetime import datetime


logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

POLL_INTERVAL = 60  # seconds between polls

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class RaceWatch:
    """A single race stage being watched."""
    race_slug: str   # e.g. "giro-d-italia"
    year:      int   # e.g. 2026
    stage:     int   # e.g. 11


@dataclass
class PollResult:
    """Result of a single poll cycle."""
    race_watch:   RaceWatch
    changed:      bool
    diff:         str        # extracted changed content, empty if unchanged
    raw_content:  str        # full page text for downstream processing
    timestamp:    datetime
    error:        str | None # None if successful


# ── Snapshot cache ────────────────────────────────────────────────────────────
# Keyed by "{race_slug}_{year}_{stage}" — stores last seen content
_snapshots: dict[str, str] = {}


# ── Content extraction ────────────────────────────────────────────────────────

def _extract_relevant_content(html_text: str) -> str:
    """
    Extract the parts of the PCS page most likely to change during a race:
    - Timeline section (live updates)
    - Situation section (groups, time gaps)
    - Race stats bar (km to go, race time)

    Returns clean text, strips nav/footer/scripts.
    Keeps it lightweight — no BeautifulSoup, just regex and string ops.
    """
    # Remove script and style blocks
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_text, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>',  '', text,      flags=re.DOTALL)

    # Remove HTML tags — keep text content
    text = re.sub(r'<[^>]+>', ' ', text)

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Try to isolate the live section
    # PCS puts "Timeline" and "Situation" as section markers
    relevant = ""

    timeline_match = re.search(r'Timeline(.{100,3000}?)(?:Statistics|Quiz|Footer|$)', text, re.DOTALL)
    if timeline_match:
        relevant += "TIMELINE: " + timeline_match.group(1).strip()

    situation_match = re.search(r'Situation(.{50,1500}?)(?:Break|Menu|Timeline|$)', text, re.DOTALL)
    if situation_match:
        relevant += " SITUATION: " + situation_match.group(1).strip()

    # Km to go / race time bar
    stats_match = re.search(r'KM TO GO(.{20,200}?)(?:START|AUTOSYNC|#ONLINE)', text)
    if stats_match:
        relevant += " STATS: " + stats_match.group(0).strip()

    # Fallback — if nothing matched, return first 2000 chars of cleaned text
    return relevant[:3000] if relevant else text[:2000]


def _compute_hash(content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()


def _compute_diff(old_content: str, new_content: str) -> str:
    """
    Find sentences that appear in new_content but not in old_content.
    Returns them joined as a string — these are the "new" updates.
    """
    old_lines = set(s.strip() for s in old_content.split('.'))
    new_lines = new_content.split('.')

    added = [
        line.strip()
        for line in new_lines
        if line.strip() and line.strip() not in old_lines and len(line.strip()) > 15
    ]

    return '. '.join(added[:20])  # cap at 20 new sentences


# ── Playwright fallback ───────────────────────────────────────────────────────

async def _poll_with_playwright(
    race_watch: RaceWatch,
    cache_key:  str,
    now:        datetime,
) -> PollResult:
    """
    Called when httpx gets a 403. Uses Playwright (real browser) to fetch
    the live page, with Firecrawl as a second fallback if Playwright times out.
    Runs the sync scraper in a thread pool so it doesn't block the event loop.
    """
    try:
        from tools.live_scraper import get_race_situation
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(
            None,
            lambda: get_race_situation(
                race_watch.race_slug,
                race_watch.year,
                race_watch.stage,
            ),
        )

        if not content or content.startswith("[Playwright failed") or content.startswith("[Firecrawl failed"):
            return PollResult(
                race_watch=race_watch,
                changed=False, diff="", raw_content="",
                timestamp=now, error=content,
            )

        content_hash = _compute_hash(content)

        if cache_key not in _snapshots:
            _snapshots[cache_key] = content
            logger.info(f"[poller] Playwright first snapshot stored for {cache_key}")
            return PollResult(
                race_watch=race_watch,
                changed=False, diff="", raw_content=content,
                timestamp=now, error=None,
            )

        old_content = _snapshots[cache_key]
        if _compute_hash(old_content) == content_hash:
            return PollResult(
                race_watch=race_watch,
                changed=False, diff="", raw_content=content,
                timestamp=now, error=None,
            )

        diff = _compute_diff(old_content, content)
        _snapshots[cache_key] = content
        logger.info(f"[poller] Playwright change detected for {cache_key}: {diff[:100]}")

        return PollResult(
            race_watch=race_watch,
            changed=True, diff=diff, raw_content=content,
            timestamp=now, error=None,
        )

    except Exception as e:
        return PollResult(
            race_watch=race_watch,
            changed=False, diff="", raw_content="",
            timestamp=now, error=f"Playwright fallback failed: {e}",
        )


# ── Core poll function ────────────────────────────────────────────────────────

async def poll_once(race_watch: RaceWatch) -> PollResult:
    """
    Poll a single PCS live page once.
    Returns PollResult with changed=True and diff if something new was detected.
    """
    url = (
        f"https://www.procyclingstats.com/race/"
        f"{race_watch.race_slug}/{race_watch.year}"
        f"/stage-{race_watch.stage}/live"
    )
    cache_key = f"{race_watch.race_slug}_{race_watch.year}_{race_watch.stage}"
    now = datetime.now()

    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            timeout=15,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)

        if response.status_code == 403:
            logger.info(f"[poller] httpx blocked (403) for {cache_key} — trying Playwright")
            return await _poll_with_playwright(race_watch, cache_key, now)

        if response.status_code != 200:
            return PollResult(
                race_watch=race_watch,
                changed=False,
                diff="",
                raw_content="",
                timestamp=now,
                error=f"HTTP {response.status_code}",
            )

        # Extract relevant content and hash it
        content      = _extract_relevant_content(response.text)
        content_hash = _compute_hash(content)

        # First poll for this race — store snapshot, no diff yet
        if cache_key not in _snapshots:
            _snapshots[cache_key] = content
            logger.info(f"[poller] First snapshot stored for {cache_key}")
            return PollResult(
                race_watch=race_watch,
                changed=False,
                diff="",
                raw_content=content,
                timestamp=now,
                error=None,
            )

        old_content = _snapshots[cache_key]
        old_hash    = _compute_hash(old_content)

        # Nothing changed
        if content_hash == old_hash:
            return PollResult(
                race_watch=race_watch,
                changed=False,
                diff="",
                raw_content=content,
                timestamp=now,
                error=None,
            )

        # Something changed — compute diff and update snapshot
        diff = _compute_diff(old_content, content)
        _snapshots[cache_key] = content

        logger.info(f"[poller] Change detected for {cache_key}: {diff[:100]}")

        return PollResult(
            race_watch=race_watch,
            changed=True,
            diff=diff,
            raw_content=content,
            timestamp=now,
            error=None,
        )

    except httpx.TimeoutException:
        return PollResult(
            race_watch=race_watch,
            changed=False,
            diff="",
            raw_content="",
            timestamp=now,
            error="Request timed out",
        )
    except Exception as e:
        return PollResult(
            race_watch=race_watch,
            changed=False,
            diff="",
            raw_content="",
            timestamp=now,
            error=str(e),
        )


# ── Watcher loop ──────────────────────────────────────────────────────────────

async def run_watcher(
    races: list[RaceWatch],
    on_change,
    interval: int = POLL_INTERVAL,
):
    """
    Main watcher loop. Polls all watched races every `interval` seconds.

    `on_change` is a coroutine called with (PollResult) whenever
    something changes. Signature: async def on_change(result: PollResult)

    Runs forever until cancelled.
    """
    logger.info(f"[poller] Watcher started — {len(races)} race(s), interval={interval}s")

    while True:
        for race in races:
            try:
                result = await poll_once(race)

                if result.error:
                    logger.warning(
                        f"[poller] {race.race_slug} stage {race.stage}: {result.error}"
                    )
                elif result.changed:
                    logger.info(
                        f"[poller] Change in {race.race_slug} "
                        f"stage {race.stage} at {result.timestamp:%H:%M:%S}"
                    )
                    await on_change(result)
                else:
                    logger.debug(
                        f"[poller] No change in {race.race_slug} "
                        f"stage {race.stage}"
                    )

            except Exception as e:
                logger.error(f"[poller] Unexpected error polling {race.race_slug}: {e}")

        await asyncio.sleep(interval)
