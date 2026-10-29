"""Small, dependency-free task ledger for the personal research system.

This module records work; it does not pretend that recording a task means it ran.
A task is only marked verified when a caller supplies verification evidence.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUSES = {"planned", "running", "blocked", "done", "verified"}


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

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    goal TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN
                        ('planned','running','blocked','done','verified')),
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

    def create(self, title: str, goal: str = "") -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("Task title cannot be empty")
        task_id, now = str(uuid.uuid4()), _now()
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        if status == "verified" and not evidence:
            raise ValueError("A task cannot be verified without evidence")
        task = self.get(task_id)
        now = _now()
        new_evidence = task["evidence"] + (evidence or [])
        new_blockers = blockers if blockers is not None else task["blockers"]
        with self._connect() as conn:
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
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_id,task_id,at,old_status,new_status,note FROM task_events WHERE task_id=? ORDER BY event_id",
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]
