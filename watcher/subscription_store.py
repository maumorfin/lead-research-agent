"""
Subscription store — tracks which users are watching which races.
Persisted to SQLite. Designed to be queried by the dispatcher.
"""
import sqlite3
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Subscription:
    chat_id:   int
    race_slug: str
    year:      int
    stage:     int

    @property
    def race_key(self) -> str:
        return f"{self.race_slug}_{self.year}_{self.stage}"


class SubscriptionStore:
    def __init__(self, db_path: str = "data/subscriptions.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                chat_id   INTEGER,
                race_slug TEXT,
                year      INTEGER,
                stage     INTEGER,
                PRIMARY KEY (chat_id, race_slug, year, stage)
            )
        """)
        self.conn.commit()

    def subscribe(self, chat_id: int, race_slug: str, year: int, stage: int):
        """Subscribe a user to live updates for a race stage."""
        self.conn.execute(
            "INSERT OR IGNORE INTO subscriptions VALUES (?,?,?,?)",
            (chat_id, race_slug, year, stage)
        )
        self.conn.commit()
        logger.info(f"[subscriptions] {chat_id} subscribed to {race_slug}/{year}/stage-{stage}")

    def unsubscribe(self, chat_id: int, race_slug: str | None = None):
        """Unsubscribe a user. If race_slug is None, removes all subscriptions."""
        if race_slug:
            self.conn.execute(
                "DELETE FROM subscriptions WHERE chat_id=? AND race_slug=?",
                (chat_id, race_slug)
            )
        else:
            self.conn.execute(
                "DELETE FROM subscriptions WHERE chat_id=?",
                (chat_id,)
            )
        self.conn.commit()

    def get_subscriptions(self, chat_id: int) -> list[Subscription]:
        """Get all subscriptions for a user."""
        rows = self.conn.execute(
            "SELECT race_slug, year, stage FROM subscriptions WHERE chat_id=?",
            (chat_id,)
        ).fetchall()
        return [Subscription(chat_id, *row) for row in rows]

    def get_subscribers(self, race_slug: str, year: int, stage: int) -> set[int]:
        """Get all chat_ids watching a specific race stage."""
        rows = self.conn.execute(
            "SELECT chat_id FROM subscriptions WHERE race_slug=? AND year=? AND stage=?",
            (race_slug, year, stage)
        ).fetchall()
        return {row[0] for row in rows}

    def get_all_watched_races(self) -> list[tuple[str, int, int]]:
        """
        Get all unique (race_slug, year, stage) combinations being watched.
        Used by the poller to know what to poll.
        """
        rows = self.conn.execute(
            "SELECT DISTINCT race_slug, year, stage FROM subscriptions"
        ).fetchall()
        return [(row[0], row[1], row[2]) for row in rows]

    def build_subscriptions_dict(self) -> dict[str, set[int]]:
        """
        Build the subscriptions dict used by the dispatcher.
        Format: {race_key: set of chat_ids}
        """
        rows = self.conn.execute(
            "SELECT race_slug, year, stage, chat_id FROM subscriptions"
        ).fetchall()
        result: dict[str, set[int]] = {}
        for race_slug, year, stage, chat_id in rows:
            key = f"{race_slug}_{year}_{stage}"
            result.setdefault(key, set()).add(chat_id)
        return result

    def has_any_subscriptions(self) -> bool:
        """True if at least one user is watching something."""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM subscriptions"
        ).fetchone()
        return row[0] > 0
