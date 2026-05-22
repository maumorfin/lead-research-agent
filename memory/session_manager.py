import time
import sqlite3
from dataclasses import dataclass


SESSION_TIMEOUT = 2 * 60 * 60  # 2 hours inactivity = new session


@dataclass
class SessionInfo:
    thread_id: str
    is_new: bool
    old_thread_id: str | None  # the expired thread, if any
    chat_id: int


class SessionManager:
    def __init__(self, db_path: str = "data/sessions.db"):
        import os
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                chat_id      INTEGER PRIMARY KEY,
                thread_id    TEXT,
                last_active  REAL
            )
        """)
        self.conn.commit()

    def get_or_create(self, chat_id: int) -> SessionInfo:
        row = self.conn.execute(
            "SELECT thread_id, last_active FROM sessions WHERE chat_id=?",
            (chat_id,)
        ).fetchone()

        now = time.time()

        if row:
            thread_id, last_active = row
            timed_out = (now - last_active) > SESSION_TIMEOUT

            if timed_out:
                old_thread = thread_id
                new_thread = f"{chat_id}_{int(now)}"
                self._save(chat_id, new_thread, now)
                return SessionInfo(
                    thread_id=new_thread,
                    is_new=True,
                    old_thread_id=old_thread,
                    chat_id=chat_id,
                )
            else:
                self._save(chat_id, thread_id, now)
                return SessionInfo(
                    thread_id=thread_id,
                    is_new=False,
                    old_thread_id=None,
                    chat_id=chat_id,
                )
        else:
            thread_id = f"{chat_id}_{int(now)}"
            self._save(chat_id, thread_id, now)
            return SessionInfo(
                thread_id=thread_id,
                is_new=True,
                old_thread_id=None,
                chat_id=chat_id,
            )

    def _save(self, chat_id: int, thread_id: str, ts: float):
        self.conn.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?,?,?)",
            (chat_id, thread_id, ts)
        )
        self.conn.commit()
