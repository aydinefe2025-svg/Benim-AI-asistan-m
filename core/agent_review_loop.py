"""Bounded, evidence-conscious multi-agent draft and critique cycle.

No autonomous background execution, model training, or unverified promotion.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from core.agent_colony import AgentColony


class AgentReviewLoop:
    def __init__(self, colony: AgentColony):
        self.colony = colony
        with colony._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS colony_reviews (
                id TEXT PRIMARY KEY, task TEXT NOT NULL,
                author_id TEXT NOT NULL, reviewer_id TEXT NOT NULL,
                draft TEXT NOT NULL, critique TEXT NOT NULL,
                revision TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL)""")

    def execute(self, author_id, reviewer_id, task, *, client, model):
        if author_id == reviewer_id:
            raise ValueError("Independent roles must have distinct agent IDs")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("Task required")
        if len(task) > 3000:
            raise ValueError("Task too long")
        draft = self.colony.run(author_id, task, client=client, model=model)
        review_task = ("Critically review the following unverified draft. "
                       "Identify missing evidence, assumptions, and errors. "
                       "Do not assert independent verification.\n"
                       + draft["output"][:12000])
        critique = self.colony.run(reviewer_id, review_task, client=client, model=model)
        revision_task = ("Revise your draft using the independent-role critique. "
                         "Distinguish supported statements, hypotheses, and gaps. "
                         "Do not invent evidence.\nOriginal draft:\n"
                         + draft["output"][:12000] + "\nCritique:\n"
                         + critique["output"][:12000])
        revision = self.colony.run(author_id, revision_task, client=client, model=model)
        record_id = str(uuid.uuid4())
        with self.colony._db() as db:
            db.execute("INSERT INTO colony_reviews VALUES (?,?,?,?,?,?,?,?,?)",
                       (record_id, task.strip(), author_id, reviewer_id,
                        draft["output"], critique["output"], revision["output"],
                        "review_pending", datetime.now(timezone.utc).isoformat()))
        return self.get(record_id)

    def get(self, review_id):
        with self.colony._db() as db:
            row = db.execute("SELECT * FROM colony_reviews WHERE id=?", (review_id,)).fetchone()
        if row is None:
            raise KeyError(review_id)
        return dict(row)
