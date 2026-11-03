"""Restore owner-scoped colony snapshots only into an empty local colony.

Validate all relationships before starting a transaction; never overwrite data.
"""
from __future__ import annotations

import sqlite3
from core.agent_review_loop import AgentReviewLoop


def restore_empty_colony(colony, snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("Invalid snapshot")
    agents, feedback, reviews = (snapshot.get(k) for k in ("agents", "feedback", "reviews"))
    if not all(isinstance(v, list) for v in (agents, feedback, reviews)):
        raise ValueError("Invalid snapshot collections")
    if len(agents) > colony.max_agents or len(feedback) > 10000 or len(reviews) > 1000:
        raise ValueError("Snapshot quota exceeded")
    ids = [a.get("id") for a in agents if isinstance(a, dict)]
    if len(ids) != len(agents) or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Invalid agent IDs")
    by_id = {a["id"]: a for a in agents}
    for a in agents:
        if a.get("parent_id") is not None and a["parent_id"] not in by_id:
            raise ValueError("Missing parent")
        if a.get("state") not in ("active", "inactive"):
            raise ValueError("Invalid agent state")
        if type(a.get("generation")) is not int or not 0 <= a["generation"] <= 3:
            raise ValueError("Invalid generation")
        if not all(isinstance(a.get(k), str) and a[k] for k in ("role", "instructions", "created_at")):
            raise ValueError("Invalid agent")
        if a["parent_id"] is None and a["generation"] != 0:
            raise ValueError("Invalid founder")
        if a["parent_id"] is not None and a["generation"] != by_id[a["parent_id"]]["generation"] + 1:
            raise ValueError("Invalid lineage")
    for row in feedback:
        if not isinstance(row, dict) or row.get("agent_id") not in by_id:
            raise ValueError("Invalid feedback agent")
        if type(row.get("id")) is not int or type(row.get("accepted")) is not int or row["accepted"] not in (0,1):
            raise ValueError("Invalid feedback")
        if not all(isinstance(row.get(k), str) for k in ("task", "lesson", "evidence", "created_at")):
            raise ValueError("Invalid feedback fields")
    for row in reviews:
        if not isinstance(row, dict) or row.get("author_id") not in by_id or row.get("reviewer_id") not in by_id:
            raise ValueError("Invalid review agents")
        if row["author_id"] == row["reviewer_id"]:
            raise ValueError("Self-review not allowed")
        if not all(isinstance(row.get(k), str) for k in
                   ("id", "task", "draft", "critique", "revision", "status", "created_at")):
            raise ValueError("Invalid review fields")
    AgentReviewLoop(colony)
    with colony._db() as db:
        db.execute("BEGIN IMMEDIATE")
        for table in ("colony_agents", "colony_feedback", "colony_reviews"):
            if db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]:
                raise RuntimeError("Restore requires empty colony")
        for a in sorted(agents, key=lambda item: item['generation']):
            db.execute("INSERT INTO colony_agents VALUES (?,?,?,?,?,?,?)",
                       tuple(a[k] for k in ("id","parent_id","generation","role","instructions","state","created_at")))
        for row in feedback:
            db.execute("INSERT INTO colony_feedback VALUES (?,?,?,?,?,?,?)",
                       tuple(row[k] for k in ("id","agent_id","task","lesson","evidence","accepted","created_at")))
        for row in reviews:
            db.execute("INSERT INTO colony_reviews VALUES (?,?,?,?,?,?,?,?,?)",
                       tuple(row[k] for k in ("id","task","author_id","reviewer_id","draft","critique","revision","status","created_at")))
    return len(agents)
