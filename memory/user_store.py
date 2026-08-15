import json
import sqlite3
import time


class UserStore:
    """
    Long-term user profile store. Persists across all sessions.
    Accumulates riders, races, language, and session summaries.
    """

    def __init__(self, db_path: str = "data/user_profiles.db"):
        import os
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                chat_id  INTEGER PRIMARY KEY,
                profile  TEXT
            )
        """)
        self.conn.commit()

    def get(self, chat_id: int) -> dict:
        row = self.conn.execute(
            "SELECT profile FROM profiles WHERE chat_id=?",
            (chat_id,)
        ).fetchone()
        return json.loads(row[0]) if row else {}

    def update(self, chat_id: int, extracted: dict):
        """Merge extracted session facts into the existing profile — never overwrites."""
        profile = self.get(chat_id)

        profile["riders_mentioned"] = list(set(
            profile.get("riders_mentioned", []) +
            extracted.get("riders", [])
        ))

        profile["races_followed"] = list(set(
            profile.get("races_followed", []) +
            extracted.get("races", [])
        ))

        if extracted.get("language"):
            profile["language"] = extracted["language"]

        past = profile.get("past_sessions", [])
        if extracted.get("summary"):
            past.append({
                "summary": extracted["summary"],
                "ts": int(time.time()),
            })
        profile["past_sessions"] = past[-5:]

        self.conn.execute(
            "INSERT OR REPLACE INTO profiles VALUES (?,?)",
            (chat_id, json.dumps(profile))
        )
        self.conn.commit()

    def format_for_prompt(self, chat_id: int) -> str:
        """Returns a compact string ready to inject into the planner prompt."""
        profile = self.get(chat_id)
        if not profile:
            return ""

        riders = ", ".join(profile.get("riders_mentioned", []))
        races  = ", ".join(profile.get("races_followed", []))
        lang   = profile.get("language", "en")
        recents = [s["summary"] for s in profile.get("past_sessions", [])[-2:]]

        parts = [f"Language: {lang}"]
        if riders:
            parts.append(f"Riders they ask about: {riders}")
        if races:
            parts.append(f"Races they follow: {races}")
        if recents:
            parts.append(f"Recent topics: {'; '.join(recents)}")

        return "User profile:\n" + "\n".join(f"- {p}" for p in parts)
