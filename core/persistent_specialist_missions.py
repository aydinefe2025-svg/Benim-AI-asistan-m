"""Resumable specialist missions with durable per-role checkpoints.

This is an explicitly invoked LLM workflow, not a background daemon or
independent self-improving agent. Each completed role is committed to SQLite.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.specialist_mission import DOMAINS, ROLES


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PersistentSpecialistMissions:
    def __init__(self, db_path, client):
        self.db_path = str(db_path)
        self.client = client
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS specialist_missions (
                    id TEXT PRIMARY KEY, question TEXT NOT NULL,
                    domain TEXT NOT NULL, model TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS specialist_steps (
                    mission_id TEXT NOT NULL REFERENCES specialist_missions(id),
                    role TEXT NOT NULL, output TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY(mission_id, role));
            """)

    def _connect(self):
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create(self, question, *, model, domain="research"):
        if domain not in DOMAINS:
            raise ValueError("Unsupported domain")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question required")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("Model required")
        mission_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute(
                "INSERT INTO specialist_missions VALUES (?,?,?,?,?,?,?)",
                (mission_id, question.strip(), domain, model.strip(),
                 "planned", _timestamp(), _timestamp()))
        return mission_id

    def get(self, mission_id):
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM specialist_missions WHERE id=?", (mission_id,)).fetchone()
            if row is None:
                raise KeyError(mission_id)
            steps = db.execute(
                "SELECT role,output,completed_at FROM specialist_steps WHERE mission_id=?",
                (mission_id,)).fetchall()
        outputs = {item["role"]: dict(item) for item in steps}
        return dict(row) | {"steps": [
            outputs[role] for role, _ in ROLES if role in outputs
        ], "verified": False}

    def run(self, mission_id):
        """Resume incomplete roles. One process/worker per mission at a time.

        A crash between an external LLM response and its SQLite commit may
        repeat that call; model calls must have no side effects.
        """
        mission = self.get(mission_id)
        if mission["status"] == "draft_unverified":
            return mission
        if mission["status"] not in {"planned", "interrupted"}:
            raise RuntimeError("Mission already running; do not start concurrent workers")
        with self._connect() as db:
            changed = db.execute(
                "UPDATE specialist_missions SET status='running',updated_at=? "
                "WHERE id=? AND status IN ('planned','interrupted')",
                (_timestamp(), mission_id)).rowcount
            if changed != 1:
                raise RuntimeError("Concurrent mission execution")
        try:
            for role, assignment in ROLES:
                current = self.get(mission_id)
                if any(step["role"] == role for step in current["steps"]):
                    continue
                prior = "\\n".join(
                    f"{step['role']}: {step['output']}" for step in current["steps"])
                prompt = (
                    f"Domain: {mission['domain']}\\nQuestion: {mission['question']}\\n"
                    f"Assignment: {assignment}\\nEarlier unverified drafts:\\n{prior}\\n"
                    "Give a bounded Turkish draft with uncertainties.")
                system = (
                    f"Role: {role}. Never invent sources or claim experiments ran. "
                    "This is unverified research. Do not perform external actions.")
                output = self.client.chat(mission["model"], system, prompt)
                if not isinstance(output, str) or not output.strip():
                    raise RuntimeError(f"Empty output from {role}")
                with self._connect() as db:
                    db.execute(
                        "INSERT INTO specialist_steps VALUES (?,?,?,?)",
                        (mission_id, role, output.strip(), _timestamp()))
            with self._connect() as db:
                db.execute(
                    "UPDATE specialist_missions SET status='draft_unverified',updated_at=? WHERE id=?",
                    (_timestamp(), mission_id))
        except Exception:
            with self._connect() as db:
                db.execute(
                    "UPDATE specialist_missions SET status='interrupted',updated_at=? WHERE id=?",
                    (_timestamp(), mission_id))
            raise
        return self.get(mission_id)

    def export_json(self, mission_id):
        """Export evidence-labelled draft; caller must archive and verify receipt."""
        return json.dumps(self.get(mission_id), ensure_ascii=False, indent=2)
