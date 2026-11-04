"""Bounded collaborative mission: planner, researcher, critic and synthesizer.

Each role performs a separate model call. Outputs are unverified drafts, not
independent factual verification or model-weight training.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from core.agent_colony import AgentColony


class CollaborativeMission:
    def __init__(self, colony: AgentColony):
        self.colony = colony
        with colony._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS colony_missions (
                id TEXT PRIMARY KEY, task TEXT NOT NULL,
                stages TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL)""")

    def execute(self, task, *, client, model):
        if not isinstance(task, str) or not task.strip() or len(task) > 1200:
            raise ValueError("Task must be 1–1200 characters")
        with self.colony._db() as db:
            agents = [dict(r) for r in db.execute(
                "SELECT id,role FROM colony_agents WHERE state='active' ORDER BY generation,id")]
        by_role = {a["role"]: a["id"] for a in agents}
        if "research" not in by_role or "evidence-reviewer" not in by_role:
            raise RuntimeError("Founder and evidence-reviewer are required")
        planner = by_role.get("research-planner", by_role["research"])
        researcher = by_role["research"]
        reviewer = by_role["evidence-reviewer"]
        stages = []
        plan = self.colony.run(planner,
            "Make a concise actionable research plan. Mark unknowns. Goal: " + task,
            client=client, model=model)
        stages.append({"role":"planner","agent_id":planner,"output":plan["output"]})
        draft = self.colony.run(researcher,
            "Investigate this goal following the plan. Distinguish unverified claims. "
            "Goal: " + task + "\nPlan:\n" + plan["output"][:6000],
            client=client, model=model, internal_review=True)
        stages.append({"role":"researcher","agent_id":researcher,"output":draft["output"]})
        critique = self.colony.run(reviewer,
            "Critique factual support, assumptions and gaps. Do not claim external "
            "verification without actual evidence. Goal: " + task
            + "\nDraft:\n" + draft["output"][:6000],
            client=client, model=model, internal_review=True)
        stages.append({"role":"reviewer","agent_id":reviewer,"output":critique["output"]})
        synthesis = self.colony.run(researcher,
            "Produce a concise revised result, explicitly separating facts, "
            "uncertainties and follow-up checks. Goal: " + task
            + "\nDraft:\n" + draft["output"][:5000]
            + "\nCritique:\n" + critique["output"][:5000],
            client=client, model=model, internal_review=True)
        stages.append({"role":"synthesis","agent_id":researcher,"output":synthesis["output"]})
        record_id = str(uuid.uuid4())
        with self.colony._db() as db:
            db.execute("INSERT INTO colony_missions VALUES (?,?,?,?,?)",
                       (record_id, task.strip(), json.dumps(stages, ensure_ascii=False),
                        "review_pending", datetime.now(timezone.utc).isoformat()))
        return {"id":record_id,"task":task.strip(),"stages":stages,
                "status":"review_pending","model_calls":4}

    def get(self, mission_id):
        with self.colony._db() as db:
            row = db.execute("SELECT * FROM colony_missions WHERE id=?",
                             (mission_id,)).fetchone()
        if row is None:
            raise KeyError(mission_id)
        result = dict(row)
        result["stages"] = json.loads(result["stages"])
        return result
