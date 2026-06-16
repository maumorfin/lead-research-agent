"""
Dynamic race store — replaces the static race registry.
Populated automatically by the calendar refresh agent.
Never requires manual updates.
"""
import sqlite3
import time
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RaceInfo:
    slug:          str
    name:          str
    year:          int
    total_stages:  int
    current_stage: int
    is_live:       bool


class RaceStore:
    def __init__(self, db_path: str = "data/races.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS races (
                slug          TEXT,
                year          INTEGER,
                name          TEXT,
                total_stages  INTEGER DEFAULT 21,
                current_stage INTEGER DEFAULT 1,
                is_live       INTEGER DEFAULT 0,
                last_confirmed REAL,
                PRIMARY KEY (slug, year)
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS calendar_meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self.conn.commit()

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_all(self) -> list[RaceInfo]:
        rows = self.conn.execute(
            "SELECT slug, name, year, total_stages, current_stage, is_live "
            "FROM races ORDER BY is_live DESC, name"
        ).fetchall()
        return [RaceInfo(*row[:5], bool(row[5])) for row in rows]

    def get_live(self) -> list[RaceInfo]:
        rows = self.conn.execute(
            "SELECT slug, name, year, total_stages, current_stage, is_live "
            "FROM races WHERE is_live=1"
        ).fetchall()
        return [RaceInfo(*row[:5], bool(row[5])) for row in rows]

    def get_upcoming(self) -> list[RaceInfo]:
        rows = self.conn.execute(
            "SELECT slug, name, year, total_stages, current_stage, is_live "
            "FROM races WHERE is_live=0"
        ).fetchall()
        return [RaceInfo(*row[:5], bool(row[5])) for row in rows]

    def get(self, slug: str) -> RaceInfo | None:
        row = self.conn.execute(
            "SELECT slug, name, year, total_stages, current_stage, is_live "
            "FROM races WHERE slug=? ORDER BY year DESC LIMIT 1",
            (slug,)
        ).fetchone()
        return RaceInfo(*row[:5], bool(row[5])) if row else None

    def has_any(self) -> bool:
        row = self.conn.execute("SELECT COUNT(*) FROM races").fetchone()
        return row[0] > 0

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert(
        self,
        slug:          str,
        name:          str,
        year:          int,
        current_stage: int,
        is_live:       bool,
        total_stages:  int = 21,
    ):
        """Insert or update a race. Never deletes existing races — only updates values."""
        self.conn.execute("""
            INSERT INTO races (slug, year, name, total_stages, current_stage, is_live, last_confirmed)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug, year) DO UPDATE SET
                name           = excluded.name,
                current_stage  = excluded.current_stage,
                is_live        = excluded.is_live,
                total_stages   = excluded.total_stages,
                last_confirmed = excluded.last_confirmed
        """, (slug, year, name, total_stages, current_stage, int(is_live), time.time()))
        self.conn.commit()

    def mark_all_not_live(self):
        """Mark all races as not live before a refresh."""
        self.conn.execute("UPDATE races SET is_live=0")
        self.conn.commit()

    # ── Metadata ──────────────────────────────────────────────────────────────

    def get_last_refresh(self) -> float | None:
        row = self.conn.execute(
            "SELECT value FROM calendar_meta WHERE key='last_refresh'"
        ).fetchone()
        return float(row[0]) if row else None

    def set_last_refresh(self, ts: float | None = None):
        self.conn.execute(
            "INSERT OR REPLACE INTO calendar_meta VALUES ('last_refresh', ?)",
            (str(ts or time.time()),)
        )
        self.conn.commit()

    def needs_refresh(self, min_age_hours: float = 20.0) -> bool:
        last = self.get_last_refresh()
        if not last:
            return True
        return (time.time() - last) > (min_age_hours * 3600)
