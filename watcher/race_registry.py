"""
Race registry — the races users can subscribe to for live updates.
Update this as the season progresses.
Current season: 2026.
"""
from dataclasses import dataclass


@dataclass
class RaceInfo:
    slug:          str
    name:          str
    year:          int
    total_stages:  int
    current_stage: int   # update this daily during a race
    is_live:       bool  # True when a stage is currently racing


# ── 2026 season registry ──────────────────────────────────────────────────────
# Update current_stage and is_live as the season progresses

RACE_REGISTRY: list[RaceInfo] = [
    RaceInfo(
        slug="giro-d-italia",
        name="Giro d'Italia",
        year=2026,
        total_stages=21,
        current_stage=11,
        is_live=True,
    ),
    RaceInfo(
        slug="tour-de-france",
        name="Tour de France",
        year=2026,
        total_stages=21,
        current_stage=1,
        is_live=False,
    ),
    RaceInfo(
        slug="vuelta-a-espana",
        name="Vuelta a España",
        year=2026,
        total_stages=21,
        current_stage=1,
        is_live=False,
    ),
    RaceInfo(
        slug="criterium-du-dauphine",
        name="Critérium du Dauphiné",
        year=2026,
        total_stages=8,
        current_stage=1,
        is_live=False,
    ),
]


def get_live_races() -> list[RaceInfo]:
    """Races currently in progress."""
    return [r for r in RACE_REGISTRY if r.is_live]


def get_upcoming_races() -> list[RaceInfo]:
    """Races not yet started."""
    return [r for r in RACE_REGISTRY if not r.is_live]


def get_race(slug: str) -> RaceInfo | None:
    """Find a race by slug."""
    return next((r for r in RACE_REGISTRY if r.slug == slug), None)


def get_all_races() -> list[RaceInfo]:
    return RACE_REGISTRY
