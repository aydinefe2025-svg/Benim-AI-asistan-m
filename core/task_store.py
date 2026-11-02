"""Small, dependency-free task ledger for the personal research system.

This module records work; it does not pretend that recording a task means it ran.
New verified transitions are disabled until independent evidence review exists.
Legacy verified records remain readable; their status is not a fresh review.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

STATUSES = {"planned", "running", "blocked", "done", "verified", "failed", "review_pending"}
ALLOWED_TRANSITIONS = {
    "planned": {"running", "blocked"},
    "running": {"done", "review_pending", "blocked", "failed"},
    "blocked": {"planned", "running", "failed"},
    "done": {"verified", "failed", "review_pending"},
    "failed": {"planned"},
    "verified": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TaskStore:
    def __init__(self, db_path: str | Path = "data/research_system.sqlite3") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    goal TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN
                        ('planned','running','blocked','done','verified','failed','review_pending')),
                    evidence TEXT NOT NULL DEFAULT '[]',
                    blockers TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    at TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id);
            """)
            # Upgrade legacy databases without deleting records or audit history.
            # Keep task history and all task rows while rebuilding the CHECK constraint.
            schema = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='tasks'"
            ).fetchone()[0]
            if "'review_pending'" not in schema:
                conn.execute("PRAGMA foreign_keys = OFF")
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("""
                        CREATE TABLE tasks_new (
                            id TEXT PRIMARY KEY,
                            title TEXT NOT NULL,
                            goal TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL CHECK(status IN
                                ('planned','running','blocked','done','verified','failed','review_pending')),
                            evidence TEXT NOT NULL DEFAULT '[]',
                            blockers TEXT NOT NULL DEFAULT '[]',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )
                    """)
                    conn.execute("""
                        INSERT INTO tasks_new(id,title,goal,status,evidence,blockers,created_at,updated_at)
                        SELECT id,title,goal,status,evidence,blockers,created_at,updated_at FROM tasks
                    """)
                    conn.execute("DROP TABLE tasks")
                    conn.execute("ALTER TABLE tasks_new RENAME TO tasks")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                finally:
                    conn.execute("PRAGMA foreign_keys = ON")

    def create(self, title: str, goal: str = "") -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("Task title cannot be empty")
        task_id, now = str(uuid.uuid4()), _now()
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO tasks(id,title,goal,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (task_id, title, goal.strip(), "planned", now, now),
            )
            conn.execute(
                "INSERT INTO task_events(task_id,at,old_status,new_status,note) VALUES(?,?,?,?,?)",
                (task_id, now, None, "planned", "Task created"),
            )
        return self.get(task_id)

    def get(self, task_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown task: {task_id}")
        result = dict(row)
        result["evidence"] = json.loads(result["evidence"])
        result["blockers"] = json.loads(result["blockers"])
        return result

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        if status is not None and status not in STATUSES:
            raise ValueError(f"Invalid status: {status}")
        with self._connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT id,title,goal,status,evidence,blockers,created_at,updated_at FROM tasks WHERE status=? ORDER BY created_at",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id,title,goal,status,evidence,blockers,created_at,updated_at FROM tasks ORDER BY created_at"
                ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item["evidence"])
            item["blockers"] = json.loads(item["blockers"])
            items.append(item)
        return items

    def transition(
        self,
        task_id: str,
        status: str,
        *,
        note: str = "",
        evidence: list[str] | None = None,
        blockers: list[str] | None = None,
    ) -> dict[str, Any]:
        if status not in STATUSES:
            raise ValueError(f"Invalid status: {status}")
        if status == "verified":
            # Arbitrary notes, URLs and model output cannot establish that a
            # primary source supports a claim. Enforce the same fail-closed
            # rule here as in KnowledgeStore, including non-UI callers.
            raise ValueError("Verified status requires independent evidence review; not available yet")
        now = _now()
        with self._connection() as conn:
            # Serialize writers and keep state validation, update and event append
            # in one transaction so concurrent workers cannot overwrite each other.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown task: {task_id}")
            task = dict(row)
            if status not in ALLOWED_TRANSITIONS[task["status"]]:
                raise ValueError(
                    f"Invalid task transition: {task['status']} -> {status}"
                )
            new_evidence = json.loads(task["evidence"]) + [
                item.strip() for item in (evidence or [])
                if isinstance(item, str) and item.strip()
            ]
            new_blockers = blockers if blockers is not None else json.loads(task["blockers"])
            conn.execute(
                "UPDATE tasks SET status=?,evidence=?,blockers=?,updated_at=? WHERE id=?",
                (status, json.dumps(new_evidence, ensure_ascii=False),
                 json.dumps(new_blockers, ensure_ascii=False), now, task_id),
            )
            conn.execute(
                "INSERT INTO task_events(task_id,at,old_status,new_status,note) VALUES(?,?,?,?,?)",
                (task_id, now, task["status"], status, note),
            )
        return self.get(task_id)

    def history(self, task_id: str) -> list[dict[str, Any]]:
        # get() validates the ID and avoids silently returning an empty history for typos.
        self.get(task_id)
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT event_id,task_id,at,old_status,new_status,note FROM task_events WHERE task_id=? ORDER BY event_id",
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]


    def finish_draft(self, task_id: str, draft: str) -> dict[str, Any]:
        """Persist the draft and review-pending state together, or neither."""
        if not isinstance(draft, str) or not draft.strip():
            raise ValueError("Draft is empty")
        now = _now()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            if row[0] != "running":
                raise ValueError("Only a running task can finish a draft")
            conn.execute("""CREATE TABLE IF NOT EXISTS research_drafts (
                task_id TEXT PRIMARY KEY REFERENCES tasks(id), content TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            conn.execute("""INSERT INTO research_drafts(task_id,content,updated_at) VALUES(?,?,?)
                ON CONFLICT(task_id) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at""",
                (task_id, draft.strip()[:12000], now))
            conn.execute("UPDATE tasks SET status='review_pending',blockers='[]',updated_at=? WHERE id=?",
                         (now, task_id))
            conn.execute("INSERT INTO task_events(task_id,at,old_status,new_status,note) VALUES(?,?,?,?,?)",
                         (task_id, now, "running", "review_pending", "Draft saved; independent evidence review pending"))
        return self.get(task_id)
