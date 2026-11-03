"""Continuously scheduled, bounded and auditable agent-generation planning.

Pure planning layer: no network access, credentials, paid resources, or unapproved
deployment. Every tick proposes candidates and records evidence; activating new
workers remains a separate, authorized action.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class ContinuousColony:
    def __init__(self, path: str, *, max_active: int = 12, max_candidates_per_tick: int = 3):
        if not 1 <= max_active <= 1000 or not 1 <= max_candidates_per_tick <= 20:
            raise ValueError("Invalid bounded resource limits")
        self.path = str(path)
        self.max_active = max_active
        self.max_candidates_per_tick = max_candidates_per_tick

    def _db(self):
        return sqlite3.connect(self.path, timeout=10)

    def initialize(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS colony_tick (
                tick_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                active_count INTEGER NOT NULL,
                candidates TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('proposed','no_capacity'))
            )""")

    def tick(self, active_agents: list[dict], *, timestamp: str | None = None) -> dict:
        """One repeatable scheduled step. No actual agent is spawned by tick()."""
        if not isinstance(active_agents, list):
            raise ValueError("active_agents must be a list")
        if any(not isinstance(a, dict) or not isinstance(a.get("id"), str)
               or not a["id"].strip() for a in active_agents):
            raise ValueError("Invalid agent identity")
        identities = [a["id"] for a in active_agents]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate agent identity")
        if len(identities) > self.max_active:
            raise ValueError("Active agent count exceeds configured limit")
        capacity = min(self.max_active - len(identities), self.max_candidates_per_tick)
        domains = ("research", "verification", "software", "archive", "simulation")
        candidates = [
            {"parent_id": identities[i % len(identities)] if identities else None,
             "role": domains[i % len(domains)],
             "generation": 1 + max((int(a.get("generation", 0)) for a in active_agents), default=0),
             "status": "awaiting_validation"}
            for i in range(capacity)
        ]
        state = "proposed" if candidates else "no_capacity"
        now = timestamp or datetime.now(timezone.utc).isoformat()
        with self._db() as db:
            cur = db.execute(
                "INSERT INTO colony_tick(created_at,active_count,candidates,state) VALUES(?,?,?,?)",
                (now, len(identities), json.dumps(candidates), state),
            )
            tick_id = cur.lastrowid
        return {"tick_id": tick_id, "state": state, "active_count": len(identities),
                "candidates": candidates, "activated": 0}

    def history(self, limit: int = 20) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("Invalid history limit")
        with self._db() as db:
            rows = db.execute(
                "SELECT tick_id,created_at,active_count,candidates,state "
                "FROM colony_tick ORDER BY tick_id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {"tick_id": row[0], "created_at": row[1], "active_count": row[2],
             "candidates": json.loads(row[3]), "state": row[4]}
            for row in rows
        ]
