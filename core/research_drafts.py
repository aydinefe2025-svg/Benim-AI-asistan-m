"""Store bounded research drafts alongside tasks on the same SQLite volume.

This persists across Streamlit sessions, but NOT across Render free-tier
filesystem replacement. Export/external durable storage is still required.
"""
import sqlite3
from contextlib import closing


def save_draft(db_path: str, task_id: str, draft: str) -> None:
    if not isinstance(draft, str) or not draft.strip():
        raise ValueError("Draft is empty")
    with closing(sqlite3.connect(str(db_path), timeout=10)) as conn, conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("""CREATE TABLE IF NOT EXISTS research_drafts (
            task_id TEXT PRIMARY KEY REFERENCES tasks(id),
            content TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""INSERT INTO research_drafts(task_id,content,updated_at)
                        VALUES(?,?,CURRENT_TIMESTAMP)
                        ON CONFLICT(task_id) DO UPDATE SET
                        content=excluded.content, updated_at=CURRENT_TIMESTAMP""",
                     (task_id, draft[:12000]))


def load_draft(db_path: str, task_id: str) -> str | None:
    with closing(sqlite3.connect(str(db_path), timeout=10)) as conn, conn:
        try:
            row = conn.execute(
                "SELECT content FROM research_drafts WHERE task_id=?", (task_id,)
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return None
            raise
    return row[0] if row else None
