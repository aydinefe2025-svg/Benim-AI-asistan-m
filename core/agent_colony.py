"""Persistent agent instances: feedback learning, bounded specialization and evaluation.

Learning here means evidence-backed retrieval of past feedback, not model-weight training.
Spawn creates a configured agent record, never a process or unrestricted replication.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AgentColony:
    def __init__(self, path, *, max_agents=12):
        if type(max_agents) is not int or not 1 <= max_agents <= 100:
            raise ValueError("Invalid agent quota")
        self.path = str(path)
        self.max_agents = max_agents
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS colony_agents (
                    id TEXT PRIMARY KEY, parent_id TEXT REFERENCES colony_agents(id),
                    generation INTEGER NOT NULL, role TEXT NOT NULL,
                    instructions TEXT NOT NULL, state TEXT NOT NULL,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS colony_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL REFERENCES colony_agents(id),
                    task TEXT NOT NULL, lesson TEXT NOT NULL,
                    evidence TEXT NOT NULL, accepted INTEGER NOT NULL,
                    created_at TEXT NOT NULL);
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def create_founder(self, role, instructions):
        if not role or not role.strip() or not instructions or not instructions.strip():
            raise ValueError("Role and instructions required")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0]:
                raise RuntimeError("Colony already initialized")
            agent_id = str(uuid.uuid4())
            db.execute("INSERT INTO colony_agents VALUES (?,?,?,?,?,?,?)",
                       (agent_id, None, 0, role.strip(), instructions.strip(), "active", now()))
        return agent_id

    def get(self, agent_id):
        with self._db() as db:
            row = db.execute("SELECT * FROM colony_agents WHERE id=?", (agent_id,)).fetchone()
        if row is None:
            raise KeyError(agent_id)
        return dict(row)

    def spawn(self, parent_id, role, instructions, *, approved=False, max_generation=3):
        if not approved:
            raise PermissionError("Spawn needs explicit authorization")
        if not role or not role.strip() or not instructions or not instructions.strip():
            raise ValueError("Role and instructions required")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            parent = db.execute("SELECT * FROM colony_agents WHERE id=?", (parent_id,)).fetchone()
            if parent is None:
                raise KeyError(parent_id)
            if parent["state"] != "active":
                raise RuntimeError("Inactive parent")
            if parent["generation"] >= max_generation:
                raise RuntimeError("Generation limit reached")
            if db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0] >= self.max_agents:
                raise RuntimeError("Agent quota reached")
            child_id = str(uuid.uuid4())
            db.execute("INSERT INTO colony_agents VALUES (?,?,?,?,?,?,?)",
                       (child_id, parent_id, parent["generation"] + 1,
                        role.strip(), instructions.strip(), "active", now()))
        return child_id

    def grow_specialists(self, *, approved=False, batch_size=3):
        """Create missing bounded specialist roles; never spawn unrestricted processes.

        Repeat calls are idempotent by role. Growth requires an explicit
        authorization and respects max_agents and the generation limit.
        """
        if not approved:
            raise PermissionError("Growth needs explicit authorization")
        if type(batch_size) is not int or not 1 <= batch_size <= 5:
            raise ValueError("Invalid growth batch")
        specs = (
            ("evidence-reviewer", "Check evidence and uncertainty; never invent sources."),
            ("test-engineer", "Design reproducible tests; report failures accurately."),
            ("memory-curator", "Organize approved lessons; never assert unverified persistence."),
            ("research-planner", "Break complex research into verifiable tasks."),
            ("risk-auditor", "Identify security, cost, privacy and reliability risks."),
            ("quality-editor", "Improve clarity without changing factual meaning."),
        )
        created = []
        # One write transaction covers detection, quota and inserts. Without it,
        # concurrent UI sessions could each observe a missing specialist and
        # create duplicate roles, even if individual spawns are transactional.
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            agents = [dict(row) for row in db.execute(
                "SELECT id,role,generation,state FROM colony_agents ORDER BY generation,id")]
            if not agents:
                raise RuntimeError("Create founder first")
            existing = {a["role"] for a in agents}
            parent = next((a for a in agents
                           if a["generation"] == 0 and a["state"] == "active"), None)
            if parent is None:
                raise RuntimeError("Active founder required")
            if parent["generation"] >= 3:
                raise RuntimeError("Generation limit reached")
            count = len(agents)
            for role, instructions in specs:
                if len(created) >= batch_size or count >= self.max_agents:
                    break
                if role in existing:
                    continue
                child_id = str(uuid.uuid4())
                db.execute("INSERT INTO colony_agents VALUES (?,?,?,?,?,?,?)",
                           (child_id, parent["id"], parent["generation"] + 1,
                            role, instructions, "active", now()))
                created.append(child_id)
                existing.add(role)
                count += 1
        return created

    def feedback(self, agent_id, task, lesson, evidence, *, accepted=False):
        self.get(agent_id)
        if not all(isinstance(v, str) and v.strip() for v in (task, lesson, evidence)):
            raise ValueError("Feedback requires task, lesson and evidence")
        with self._db() as db:
            cursor = db.execute(
                "INSERT INTO colony_feedback(agent_id,task,lesson,evidence,accepted,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (agent_id, task.strip(), lesson.strip(), evidence.strip(),
                 int(bool(accepted)), now()))
            return cursor.lastrowid

    def lessons(self, agent_id, *, limit=5):
        self.get(agent_id)
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Invalid lesson limit")
        with self._db() as db:
            rows = db.execute(
                "SELECT task,lesson,evidence FROM colony_feedback "
                "WHERE agent_id=? AND accepted=1 ORDER BY id DESC LIMIT ?",
                (agent_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def evaluate_learning(self, agent_id, *, min_evidence=2):
        """Measure accepted, evidence-backed lessons; never claim weight training.

        A distinct evidence string is required for each counted lesson.
        Readiness indicates reusable retrieval memory, not autonomous intelligence.
        """
        self.get(agent_id)
        if type(min_evidence) is not int or not 1 <= min_evidence <= 20:
            raise ValueError("Invalid evidence threshold")
        with self._db() as db:
            rows = db.execute(
                "SELECT lesson,evidence FROM colony_feedback "
                "WHERE agent_id=? AND accepted=1 ORDER BY id DESC", (agent_id,)
            ).fetchall()
        unique_evidence = {row["evidence"].strip() for row in rows if row["evidence"].strip()}
        return {
            "agent_id": agent_id,
            "accepted_lessons": len(rows),
            "distinct_evidence": len(unique_evidence),
            "retrieval_ready": len(unique_evidence) >= min_evidence,
            "model_weights_updated": False,
        }


    def approve_feedback(self, feedback_id, *, approved=False):
        """Activate one previously pending lesson after an explicit owner action."""
        if not approved:
            raise PermissionError("Explicit lesson approval required")
        if type(feedback_id) is not int or feedback_id <= 0:
            raise ValueError("Invalid feedback identifier")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id,agent_id,accepted FROM colony_feedback WHERE id=?",
                (feedback_id,),
            ).fetchone()
            if row is None:
                raise KeyError(feedback_id)
            if row["accepted"]:
                return {"id": row["id"], "agent_id": row["agent_id"],
                        "status": "already_accepted"}
            db.execute("UPDATE colony_feedback SET accepted=1 WHERE id=?",
                       (feedback_id,))
            return {"id": row["id"], "agent_id": row["agent_id"],
                    "status": "accepted"}

    def run(self, agent_id, task, *, client, model, internal_review=False,
            include_lessons=True, additional_lessons=()):
        """Run one bounded draft, optionally without accepted feedback lessons.

        The switch exists for controlled paired evaluation. Normal calls keep
        the historical memory-enabled behavior; disabling memory never changes
        or deletes stored feedback.
        """
        if type(include_lessons) is not bool:
            raise ValueError("include_lessons must be boolean")
        if (not isinstance(additional_lessons, tuple) or len(additional_lessons) > 1
                or any(not isinstance(item, str) or not item.strip() or len(item) > 600
                       for item in additional_lessons)):
            raise ValueError("At most one bounded candidate lesson is allowed")
        if additional_lessons and not include_lessons:
            raise ValueError("Candidate lessons require the baseline memory context")
        agent = self.get(agent_id)
        if agent["state"] != "active":
            raise RuntimeError("Agent is inactive")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("Task required")
        if len(task) > (26000 if internal_review else 3000):
            raise ValueError("Task too long")
        lessons = self.lessons(agent_id) if include_lessons else []
        if additional_lessons:
            lessons = [*lessons, {
                "task": "isolated_candidate_evaluation",
                "lesson": additional_lessons[0],
                "evidence": "unapproved; evaluation only",
            }]
        memory = json.dumps(lessons, ensure_ascii=False)
        prompt = (f"Task: {task.strip()}\n"
                  "Accepted past lessons (not verified facts):\n"
                  f"{memory}\n"
                  "Separate facts, hypotheses and missing evidence.")
        output = client.chat(model, agent["instructions"] +
                             " Do not claim unverified results as facts.", prompt)
        if not isinstance(output, str) or not output.strip():
            raise RuntimeError("Empty model response")
        if len(output) > 12000:
            raise RuntimeError("Model response exceeds review storage limit")
        return {"agent_id": agent_id, "output": output, "status": "draft_unverified",
                "lessons_used": len(lessons), "model": model}
