"""Explicit, conservative recovery for interrupted research tasks.

Only stale running tasks are blocked; never silently re-run a provider call.
"""
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, timedelta


def recover_stale_running(db_path, *, stale_after_seconds=3600, now=None):
    if stale_after_seconds < 1:
        raise ValueError("stale_after_seconds must be positive")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must have a timezone")
    threshold = now.astimezone(timezone.utc) - timedelta(seconds=stale_after_seconds)
    recovered = []
    with closing(sqlite3.connect(str(db_path), timeout=15)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT id,updated_at FROM tasks WHERE status='running' ORDER BY id"
        ).fetchall()
        for task_id, updated_at in rows:
            stamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("Stored timestamps must be timezone-aware")
            if stamp.astimezone(timezone.utc) > threshold:
                continue
            changed = conn.execute(
                """UPDATE tasks SET status='blocked',
                   blockers='["Interrupted task; review before retry"]',
                   updated_at=? WHERE id=? AND status='running'""",
                (now.isoformat(), task_id),
            ).rowcount
            if changed:
                conn.execute(
                    """INSERT INTO task_events(task_id,at,old_status,new_status,note)
                       VALUES(?,?,?,?,?)""",
                    (task_id, now.isoformat(), "running", "blocked",
                     "Stale running task recovered; manual retry required"),
                )
                recovered.append(task_id)
    return recovered
