"""Restore owner-scoped colony snapshots only into an empty local colony.

Validate all relationships before starting a transaction; never overwrite data.
"""
from __future__ import annotations

import json
import sqlite3
from core.agent_review_loop import AgentReviewLoop
from core.collaborative_mission import CollaborativeMission


def restore_empty_colony(colony, snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("Invalid snapshot")
    agents, feedback, reviews = (snapshot.get(k) for k in ("agents", "feedback", "reviews"))
    # Older snapshots predate collaborative missions and remain restorable.
    missions = snapshot.get("missions", [])
    if not all(isinstance(v, list) for v in (agents, feedback, reviews, missions)):
        raise ValueError("Invalid snapshot collections")
    if (len(agents) > colony.max_agents or len(feedback) > 10000
            or len(reviews) > 1000 or len(missions) > 1000):
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
    seen_mission_ids = set()
    for row in missions:
        if not isinstance(row, dict) or not all(
                isinstance(row.get(k), str) and row[k]
                for k in ("id", "task", "stages", "status", "created_at")):
            raise ValueError("Invalid mission")
        if row["id"] in seen_mission_ids or len(row["task"]) > 1200:
            raise ValueError("Duplicate or oversized mission")
        seen_mission_ids.add(row["id"])
        if row["status"] not in ("review_pending", "blocked", "running") or len(row["stages"]) > 60000:
            raise ValueError("Invalid mission status or stages")
        try:
            stages = json.loads(row["stages"])
        except (ValueError, TypeError):
            raise ValueError("Invalid mission JSON") from None
        roles = [s.get("role") if isinstance(s, dict) else None for s in stages] if isinstance(stages, list) else []
        if (not isinstance(stages, list) or len(stages) > 4 or
                roles != ["planner", "researcher", "reviewer", "synthesis"][:len(stages)] or
                (row["status"] == "review_pending" and len(stages) != 4)):
            raise ValueError("Invalid mission stage sequence")
        for stage in stages:
            if (not isinstance(stage.get("agent_id"), str)
                    or stage["agent_id"] not in by_id
                    or not isinstance(stage.get("output"), str)
                    or not stage["output"].strip()
                    or len(stage["output"]) > 12000):
                raise ValueError("Invalid mission stage")
    CollaborativeMission(colony)
    AgentReviewLoop(colony)
    with colony._db() as db:
        db.execute("BEGIN IMMEDIATE")
        for table in ("colony_agents", "colony_feedback", "colony_reviews", "colony_missions"):
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
        for row in missions:
            # An imported in-flight process is no longer running in this process;
            # require explicit operator resume rather than making duplicate calls.
            db.execute("INSERT INTO colony_missions VALUES (?,?,?,?,?)",
                       (row["id"], row["task"], row["stages"],
                        "blocked" if row["status"] == "running" else row["status"],
                        row["created_at"]))
        # Verify inside the same transaction, so any SQL trigger or database
        # mutation that changes a restored row causes a rollback, not a false
        # success or a partially committed restore. Do not silently drop fields.
        collections = (
            ("colony_agents", agents), ("colony_feedback", feedback),
            ("colony_reviews", reviews),
            ("colony_missions", [
                {**item, "status": "blocked"} if item["status"] == "running" else item
                for item in missions
            ]),
        )
        for table, expected in collections:
            saved = [dict(row) for row in db.execute("SELECT * FROM " + table)]
            canonical = lambda rows: sorted(rows, key=lambda row: str(row["id"]))
            if canonical(saved) != canonical(expected):
                raise RuntimeError("Colony snapshot readback mismatch")
    return len(agents)


def restore_owner_backup(colony, snapshot_store, owner_key, *, approved=False, revision=None):
    """Restore one authenticated owner's PostgreSQL backup with explicit consent.

    The caller must authenticate the owner before passing owner_key. Never
    retrieve data for another owner or overwrite an existing colony. The
    shared transactional restore verifies every row before committing.
    """
    if approved is not True:
        raise PermissionError("Explicit restore confirmation required")
    if (not isinstance(owner_key, str) or not owner_key.strip()
            or len(owner_key) > 128):
        raise ValueError("Authenticated owner key required")
    if revision is None:
        snapshot = snapshot_store.load(owner_key)
    else:
        if type(revision) is not int or revision < 1:
            raise ValueError("Invalid snapshot revision")
        snapshot = snapshot_store.load_archived(owner_key, revision)
    if snapshot is None:
        raise LookupError("No backup for authenticated owner")
    return restore_empty_colony(colony, snapshot)


def restore_colony_json_bytes(colony, raw):
    """Import a bounded, explicitly supplied UTF-8 JSON backup into an empty colony.

    The data is never executed; relational validation is delegated to the same
    fail-closed, transactional restore used by authenticated PostgreSQL backups.
    """
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > 2_000_000:
        raise ValueError("Invalid or oversized backup")
    try:
        snapshot = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON backup") from exc
    return restore_empty_colony(colony, snapshot)