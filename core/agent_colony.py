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

    def run(self, agent_id, task, *, client, model):
        agent = self.get(agent_id)
        if agent["state"] != "active":
            raise RuntimeError("Agent is inactive")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("Task required")
        if len(task) > 3000:
            raise ValueError("Task too long")
        memory = json.dumps(self.lessons(agent_id), ensure_ascii=False)
        prompt = (f"Task: {task.strip()}\\nAccepted past lessons (not verified facts): "
                  f"{memory}\\nSeparate facts, hypotheses and missing evidence.")
        output = client.chat(model, agent["instructions"] +
                             " Do not claim unverified results as facts.", prompt)
        if not isinstance(output, str) or not output.strip():
            raise RuntimeError("Empty model response")
        if len(output) > 12000:
            raise RuntimeError("Model response exceeds review storage limit")
        return {"agent_id": agent_id, "output": output, "status": "draft_unverified",
                "lessons_used": len(self.lessons(agent_id)), "model": model}
