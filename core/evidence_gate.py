"""Evidence gate: an LLM draft is never verified without a recorded review.

This module intentionally requires explicit independently checked evidence.
It does not fetch or verify URLs automatically.
"""
import sqlite3
from datetime import datetime, timezone


def record_evidence_review(db_path, task_id, *, source_url, evidence_note, reviewer, accepted):
    if not all(isinstance(x, str) and x.strip() for x in
               (task_id, source_url, evidence_note, reviewer)):
        raise ValueError("Task, source, evidence note and reviewer are required")
    if not source_url.startswith(("https://", "http://")):
        raise ValueError("A source URL is required")
    if type(accepted) is not bool:
        raise ValueError("accepted must be boolean")
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(str(db_path), timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""CREATE TABLE IF NOT EXISTS evidence_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            source_url TEXT NOT NULL,
            evidence_note TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            accepted INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL)""")
        row = conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        if row[0] != "review_pending":
            raise ValueError("Only review_pending tasks can be reviewed")
        conn.execute("""INSERT INTO evidence_reviews
            (task_id,source_url,evidence_note,reviewer,accepted,reviewed_at)
            VALUES (?,?,?,?,?,?)""",
            (task_id, source_url, evidence_note, reviewer, int(accepted), now))
        if accepted:
            conn.execute("UPDATE tasks SET status='verified',updated_at=? WHERE id=?",
                         (now, task_id))
            conn.execute("""INSERT INTO task_events
                (task_id,at,old_status,new_status,note) VALUES (?,?,?,?,?)""",
                (task_id, now, "review_pending", "verified",
                 "Independent evidence review accepted"))
        else:
            conn.execute("""INSERT INTO task_events
                (task_id,at,old_status,new_status,note) VALUES (?,?,?,?,?)""",
                (task_id, now, "review_pending", "review_pending",
                 "Evidence review rejected; task remains pending"))
    return {"task_id": task_id, "status": "verified" if accepted else "review_pending",
            "reviewed_at": now}
