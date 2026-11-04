"""Bounded, resumable four-stage CANO research missions.

Each model call is checkpointed before the next one. A failed model call leaves
an auditable blocked mission that an operator can explicitly resume.
No claim of factual verification, independent model training or autonomous work.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from core.agent_colony import AgentColony


STAGE_ROLES = ("planner", "researcher", "reviewer", "synthesis")


class CollaborativeMission:
    def __init__(self, colony: AgentColony):
        self.colony = colony
        with colony._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS colony_missions (
                id TEXT PRIMARY KEY, task TEXT NOT NULL,
                stages TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL)""")

    def _agents(self):
        with self.colony._db() as db:
            agents = [dict(row) for row in db.execute(
                "SELECT id,role FROM colony_agents WHERE state='active' "
                "ORDER BY generation,id")]
        roles = {agent["role"]: agent["id"] for agent in agents}
        if "research" not in roles or "evidence-reviewer" not in roles:
            raise RuntimeError("Founder and evidence-reviewer are required")
        return (roles.get("research-planner", roles["research"]),
                roles["research"], roles["evidence-reviewer"])

    def execute(self, task, *, client, model):
        if not isinstance(task, str) or not task.strip() or len(task) > 1200:
            raise ValueError("Task must be 1–1200 characters")
        self._agents()  # Validate before creating a mission record.
        mission_id = str(uuid.uuid4())
        with self.colony._db() as db:
            db.execute("INSERT INTO colony_missions VALUES (?,?,?,?,?)",
                       (mission_id, task.strip(), "[]", "running",
                        datetime.now(timezone.utc).isoformat()))
        return self._run(mission_id, client=client, model=model)

    def resume(self, mission_id, *, client, model):
        """Resume only a blocked mission, never duplicate a running mission."""
        with self.colony._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM colony_missions WHERE id=?",
                             (mission_id,)).fetchone()
            if row is None:
                raise KeyError(mission_id)
            if row["status"] == "review_pending":
                result = self.get(mission_id)
                result["model_calls"] = 0
                return result
            if row["status"] != "blocked":
                raise RuntimeError("Mission is already running")
            db.execute("UPDATE colony_missions SET status='running' "
                       "WHERE id=? AND status='blocked'", (mission_id,))
        return self._run(mission_id, client=client, model=model)

    def _run(self, mission_id, *, client, model):
        calls = 0
        try:
            planner, researcher, reviewer = self._agents()
            record = self.get(mission_id)
            if record["status"] != "running":
                raise RuntimeError("Mission is not running")
            stages = record["stages"]
            expected = list(STAGE_ROLES)
            if (not isinstance(stages, list) or len(stages) > 4 or
                    [stage.get("role") for stage in stages] != expected[:len(stages)]):
                raise ValueError("Invalid saved mission stages")
            task = record["task"]
            for index in range(len(stages), len(STAGE_ROLES)):
                if index == 0:
                    agent_id = planner
                    prompt = ("Make a concise actionable research plan. Mark unknowns. Goal: "
                              + task)
                elif index == 1:
                    agent_id = researcher
                    prompt = ("Investigate this goal following the plan. Distinguish "
                              "unverified claims. Goal: " + task
                              + "\nPlan:\n" + stages[0]["output"][:6000])
                elif index == 2:
                    agent_id = reviewer
                    prompt = ("Critique factual support, assumptions and gaps. Do not claim "
                              "external verification without actual evidence. Goal: " + task
                              + "\nDraft:\n" + stages[1]["output"][:6000])
                else:
                    agent_id = researcher
                    prompt = ("Produce a concise revised result, explicitly separating "
                              "facts, uncertainties and follow-up checks. Goal: " + task
                              + "\nDraft:\n" + stages[1]["output"][:5000]
                              + "\nCritique:\n" + stages[2]["output"][:5000])
                result = self.colony.run(agent_id, prompt, client=client, model=model,
                                         internal_review=(index > 0))
                calls += 1
                stages.append({"role": STAGE_ROLES[index], "agent_id": agent_id,
                               "output": result["output"]})
                with self.colony._db() as db:
                    cursor = db.execute(
                        "UPDATE colony_missions SET stages=? "
                        "WHERE id=? AND status='running'",
                        (json.dumps(stages, ensure_ascii=False), mission_id))
                    if cursor.rowcount != 1:
                        raise RuntimeError("Mission state changed during execution")
            with self.colony._db() as db:
                cursor = db.execute(
                    "UPDATE colony_missions SET status='review_pending' "
                    "WHERE id=? AND status='running'", (mission_id,))
                if cursor.rowcount != 1:
                    raise RuntimeError("Mission state changed during completion")
            return {"id": mission_id, "task": task, "stages": stages,
                    "status": "review_pending", "model_calls": calls}
        except Exception:
            with self.colony._db() as db:
                db.execute("UPDATE colony_missions SET status='blocked' "
                           "WHERE id=? AND status='running'", (mission_id,))
            raise

    def recover_stale(self, *, older_than_seconds=3600, current_time=None):
        """Mark abandoned running missions blocked after a conservative interval.

        Does not invoke a model or automatically retry potentially expensive work.
        """
        if type(older_than_seconds) is not int or older_than_seconds < 600:
            raise ValueError("Recovery threshold too short")
        reference = current_time or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            raise ValueError("Reference timestamp must have a timezone")
        recovered = []
        with self.colony._db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id,created_at FROM colony_missions WHERE status='running'"
            ).fetchall()
            for row in rows:
                created = datetime.fromisoformat(row["created_at"])
                if created.tzinfo is None:
                    continue
                if (reference - created).total_seconds() >= older_than_seconds:
                    db.execute("UPDATE colony_missions SET status='blocked' "
                               "WHERE id=? AND status='running'", (row["id"],))
                    recovered.append(row["id"])
        return recovered

    def interrupted(self, *, limit=10):
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError("Invalid mission list limit")
        with self.colony._db() as db:
            rows = db.execute(
                "SELECT id,task,status FROM colony_missions "
                "WHERE status IN ('running','blocked') "
                "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def get(self, mission_id):
        with self.colony._db() as db:
            row = db.execute("SELECT * FROM colony_missions WHERE id=?",
                             (mission_id,)).fetchone()
        if row is None:
            raise KeyError(mission_id)
        result = dict(row)
        result["stages"] = json.loads(result["stages"])
        return result
