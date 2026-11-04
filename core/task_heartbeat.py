"""Atomic liveness heartbeat for active research tasks.

Call only while a worker actually owns an active task. This module does not
create a background worker or claim that a provider is alive.
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone


def touch_running(db_path, task_id, *, now=None):
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id is required")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    with closing(sqlite3.connect(str(db_path), timeout=15)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        changed = conn.execute(
            "UPDATE tasks SET updated_at=? WHERE id=? AND status='running'",
            (now.astimezone(timezone.utc).isoformat(), task_id),
        ).rowcount
    return changed == 1
