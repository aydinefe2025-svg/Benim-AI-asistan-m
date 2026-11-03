"""Validated, non-destructive import of portable research backups.

Imported tasks are reset to planned: exported statuses and model drafts are
not proof of verification. All inserts are committed in one SQLite transaction.
"""
from __future__ import annotations
import json
import sqlite3
from contextlib import closing
import uuid
from datetime import datetime, timezone
from core.task_store import TaskStore
from core.archive_integrity import check_archive_integrity

MAX_BYTES = 3_000_000
MAX_TASKS = 200


def import_research_archive(store: TaskStore, raw: bytes) -> int:
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise ValueError("Invalid archive size")
    try:
        archive = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON archive") from exc
    if not isinstance(archive, dict) or archive.get("schema") != "research-task-export-v1":
        raise ValueError("Unsupported archive schema")
    check_archive_integrity(archive)
    tasks = archive.get("tasks")
    if not isinstance(tasks, list) or len(tasks) > MAX_TASKS:
        raise ValueError("Invalid task collection")
    validated = []
    for item in tasks:
        if not isinstance(item, dict):
            raise ValueError("Invalid task entry")
        title, goal, draft = item.get("title"), item.get("goal"), item.get("draft")
        if not isinstance(title, str) or not 0 < len(title.strip()) <= 200:
            raise ValueError("Invalid title")
        if not isinstance(goal, str) or len(goal) > 1000:
            raise ValueError("Invalid goal")
        if draft is not None and (not isinstance(draft, str) or len(draft) > 12000):
            raise ValueError("Invalid draft")
        # Preserve the complete original record as untrusted provenance. Do not
        # restore its status/evidence into the active verification state.
        provenance = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        validated.append((title.strip(), goal, draft, provenance))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # TaskStore ensures the tasks/events schema exists.
    with closing(sqlite3.connect(store.db_path, timeout=10)) as conn, conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""CREATE TABLE IF NOT EXISTS research_drafts (
            task_id TEXT PRIMARY KEY REFERENCES tasks(id),
            content TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        for title, goal, draft, provenance in validated:
            task_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO tasks(id,title,goal,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (task_id, title, goal, "planned", now, now),
            )
            conn.execute(
                "INSERT INTO task_events(task_id,at,old_status,new_status,note) VALUES(?,?,?,?,?)",
                (task_id, now, None, "planned",
                 "Imported from backup; re-verification required. "
                 "Untrusted original record: " + provenance),
            )
            if draft:
                conn.execute(
                    "INSERT INTO research_drafts(task_id,content) VALUES(?,?)",
                    (task_id, draft),
                )
    return len(validated)
