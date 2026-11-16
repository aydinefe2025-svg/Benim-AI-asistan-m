"""Persistent agent instances: feedback learning, bounded specialization and evaluation.

Learning here means evidence-backed retrieval of past feedback, not model-weight training.
Spawn creates a configured agent record, never a process or unrestricted replication.
"""
from __future__ import annotations

import json
import re
import unicodedata
from contextlib import contextmanager
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_LESSON_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "into", "is", "it", "me", "of", "on", "or", "the", "this", "that",
    "to", "what", "when", "where", "which", "who", "why", "with", "please",
    "task", "question", "research", "gorev", "gorevi", "soru", "konu", "ders",
    "bir", "ve", "ile", "icin", "bu", "su", "ne", "nedir", "hakkinda",
}


def _lesson_terms(text):
    normalized = text.translate(str.maketrans({"ı": "i", "İ": "i"})).casefold()
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(character for character in normalized
                         if not unicodedata.combining(character))
    return {
        token for token in re.findall(r"[a-z0-9]{2,}", normalized)
        if token not in _LESSON_STOP_WORDS
    }


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
                CREATE TABLE IF NOT EXISTS colony_benchmarks (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL REFERENCES colony_agents(id),
                    dataset_ref TEXT NOT NULL,
                    benchmark_sha256 TEXT NOT NULL,
                    baseline_passed INTEGER NOT NULL,
                    candidate_passed INTEGER NOT NULL,
                    total_cases INTEGER NOT NULL,
                    baseline_reproducible INTEGER NOT NULL,
                    candidate_reproducible INTEGER NOT NULL,
                    improved_cases INTEGER NOT NULL,
                    regressed_cases INTEGER NOT NULL,
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

    def record_benchmark(self, agent_id, dataset_ref, measured):
        """Save a bounded, metadata-only A/B result; never save model text.

        Receipts are measurements, not a model-weight update or an instruction
        to activate a lesson. They are kept with the owner's colony snapshot.
        """
        self.get(agent_id)
        if (not isinstance(dataset_ref, str)
                or not re.fullmatch(r"[A-Za-z0-9._:-]{1,120}", dataset_ref)):
            raise ValueError("Benchmark reference must be a short opaque label")
        if (not isinstance(measured, dict)
                or measured.get("comparison") != "accepted_feedback_retrieval_only"
                or measured.get("model_weights_updated") is not False):
            raise ValueError("Invalid A/B measurement")
        digest = measured.get("benchmark_sha256")
        baseline = measured.get("baseline")
        candidate = measured.get("candidate")
        reproducible = measured.get("reproducible")
        if (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
                or not isinstance(reproducible, dict)
                or any(type(reproducible.get(k)) is not bool
                       for k in ("baseline", "candidate"))):
            raise ValueError("Invalid A/B evidence")
        try:
            total = baseline.total
            initial = baseline.passed
            improved = candidate.passed
            base_repeated = baseline.reproducible
            trial_repeated = candidate.reproducible
            improvements = len(measured["improved_case_ids"])
            regressions = len(measured["regressed_case_ids"])
        except (AttributeError, KeyError, TypeError) as exc:
            raise ValueError("Incomplete A/B measurement") from exc
        if (any(type(v) is not int for v in
                (total, initial, improved, improvements, regressions))
                or not 1 <= total <= 10
                or candidate.total != total
                or not 0 <= initial <= total or not 0 <= improved <= total
                or not 0 <= improvements + regressions <= total
                or improved - initial != improvements - regressions
                or type(base_repeated) is not bool
                or type(trial_repeated) is not bool
                or reproducible["baseline"] != base_repeated
                or reproducible["candidate"] != trial_repeated):
            raise ValueError("Inconsistent A/B measurement")
        record = {
            "id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "dataset_ref": dataset_ref,
            "benchmark_sha256": digest,
            "baseline_passed": initial,
            "candidate_passed": improved,
            "total_cases": total,
            "baseline_reproducible": int(base_repeated),
            "candidate_reproducible": int(trial_repeated),
            "improved_cases": improvements,
            "regressed_cases": regressions,
            "created_at": now(),
        }
        fields = tuple(record)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM colony_benchmarks").fetchone()[0] >= 100:
                raise RuntimeError("Benchmark receipt quota reached; export first")
            db.execute(
                "INSERT INTO colony_benchmarks (" + ",".join(fields)
                + ") VALUES (" + ",".join("?" for _ in fields) + ")",
                tuple(record.values()))
            observed = db.execute(
                "SELECT * FROM colony_benchmarks WHERE id=?", (record["id"],)
            ).fetchone()
            if observed is None or dict(observed) != record:
                raise RuntimeError("Benchmark receipt failed local readback")
        return record

    def list_benchmarks(self, agent_id, *, limit=10):
        """Read per-agent non-sensitive A/B measurement summaries."""
        self.get(agent_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid benchmark list limit")
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM colony_benchmarks WHERE agent_id=? "
                "ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (agent_id, limit)).fetchall()
        return [dict(row) for row in rows]

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

    def _lineage_ids(self, agent_id):
        """Return this agent and its parents, never sibling or unrelated branches.

        The authorized agent tree has at most three descendant generations.
        Reject malformed/cyclic parent links rather than leaking other lessons.
        """
        lineage = []
        with self._db() as db:
            current = agent_id
            while current is not None:
                if current in lineage or len(lineage) >= 4:
                    raise RuntimeError("Invalid bounded agent lineage")
                row = db.execute(
                    "SELECT parent_id FROM colony_agents WHERE id=?", (current,)
                ).fetchone()
                if row is None:
                    raise KeyError(current)
                lineage.append(current)
                current = row["parent_id"]
        return tuple(lineage)

    def lessons(self, agent_id, *, limit=5, task=None):
        """Return approved relevant lessons from this agent or its ancestors.

        Accepted evidence belongs only to this owner's local colony. Parent
        lessons are inherited by descendants, not siblings. The nearest
        specialist wins equal-relevance ties, and unrelated lessons are omitted.
        No unapproved feedback is ever used for model prompts.
        """
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Invalid lesson limit")
        if task is not None and (not isinstance(task, str) or not task.strip()):
            raise ValueError("Task is required for lesson matching")
        lineage = self._lineage_ids(agent_id)
        placeholders = ",".join("?" for _ in lineage)
        with self._db() as db:
            rows = db.execute(
                "SELECT agent_id,task,lesson,evidence FROM colony_feedback "
                f"WHERE accepted=1 AND agent_id IN ({placeholders}) "
                "ORDER BY id DESC LIMIT 500", lineage
            ).fetchall()
        ranked = []
        query_terms = _lesson_terms(task) if task is not None else None
        for recency, row in enumerate(rows):
            item = dict(row)
            distance = lineage.index(item.pop("agent_id"))
            if query_terms is None:
                score = 0
            elif item["task"].strip() == "*":
                score = 0
            else:
                score = len(query_terms & _lesson_terms(item["task"] + " " + item["lesson"]))
                if not score:
                    continue
            ranked.append((-score, distance, recency, item))
        ranked.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
        return [item for _, _, _, item in ranked[:limit]]

    def evaluate_learning(self, agent_id, *, min_evidence=2):
        """Count accessible approved feedback; never assert model-weight training.

        Parent-approved evidence is available to descendants but not siblings.
        Readiness is retrieval-memory availability, not measured task accuracy.
        """
        if type(min_evidence) is not int or not 1 <= min_evidence <= 20:
            raise ValueError("Invalid evidence threshold")
        lineage = self._lineage_ids(agent_id)
        placeholders = ",".join("?" for _ in lineage)
        with self._db() as db:
            rows = db.execute(
                "SELECT agent_id,lesson,evidence FROM colony_feedback "
                f"WHERE accepted=1 AND agent_id IN ({placeholders}) ORDER BY id DESC",
                lineage
            ).fetchall()
        unique_evidence = {row["evidence"].strip() for row in rows if row["evidence"].strip()}
        return {
            "agent_id": agent_id,
            "accepted_lessons": len(rows),
            "inherited_lessons": sum(row["agent_id"] != agent_id for row in rows),
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
        lessons = self.lessons(agent_id, task=task) if include_lessons else []
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


