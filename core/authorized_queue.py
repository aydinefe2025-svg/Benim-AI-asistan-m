"""Bounded, owner-scoped SQLite work queue for explicitly approved tasks.

No background daemon, provider credentials, network I/O, or automatic worker
spawning. A lease protects local worker ownership, not exactly-once external
provider effects; after an expired lease the task is blocked for human review.
Owner keys and approval MUST be supplied by an authenticated calling layer.
"""
from __future__ import annotations

import hashlib
import math
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable


def _finite_now(now):
    """Reject NaN and infinite test-clock overrides before reading or writing DB."""
    try:
        when = time.time() if now is None else float(now)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Finite clock value required") from exc
    if not math.isfinite(when):
        raise ValueError("Finite clock value required")
    return when


class AuthorizedQueue:
    def __init__(self, path: str | Path, *, owner_key: str, max_jobs: int = 100):
        if not isinstance(owner_key, str) or not owner_key.strip() or len(owner_key) > 128:
            raise ValueError("Nonempty authenticated owner key required")
        if type(max_jobs) is not int or not 1 <= max_jobs <= 1000:
            raise ValueError("Invalid job quota")
        if str(path) == ":memory:":
            raise ValueError("Persistent file-backed SQLite database required")
        self.path = str(path)
        self.owner_key = owner_key
        self.max_jobs = max_jobs
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS authorized_jobs (
                    id TEXT PRIMARY KEY,
                    owner_key TEXT NOT NULL,
                    idem_key TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('queued','running','review_pending','blocked')),
                    max_calls INTEGER NOT NULL CHECK(max_calls BETWEEN 1 AND 3),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    eligible_after REAL NOT NULL DEFAULT 0,
                    lease_token TEXT,
                    worker_id TEXT,
                    lease_until REAL,
                    result_digest TEXT,
                    draft TEXT,
                    UNIQUE(owner_key,idem_key)
                );
                CREATE INDEX IF NOT EXISTS idx_authorized_jobs_claim
                    ON authorized_jobs(owner_key,state,eligible_after);
                CREATE TABLE IF NOT EXISTS authorized_job_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_key TEXT NOT NULL,
                    job_id TEXT NOT NULL REFERENCES authorized_jobs(id),
                    at REAL NOT NULL,
                    state TEXT NOT NULL,
                    code TEXT NOT NULL
                );
            """)

    @contextmanager
    def _db(self):
        path = Path(self.path)
        if path.is_symlink():
            raise ValueError("Task queue database must not be a symbolic link")
        if os.name == "posix":
            # Restrict new and existing queue files before SQLite opens them or
            # creates a rollback journal containing owner-private records.
            # Reject a swapped final-component symlink when opening the file.
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                os.fchmod(fd, 0o600)
            finally:
                os.close(fd)
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _record(self, db, task_id, when, state, code):
        db.execute("INSERT INTO authorized_job_events(owner_key,job_id,at,state,code) VALUES(?,?,?,?,?)",
                   (self.owner_key, task_id, when, state, code))

    @staticmethod
    def _public(row):
        if row is None:
            return None
        data = dict(row)
        data.pop("lease_token", None)
        data.pop("owner_key", None)
        return data

    def enqueue(self, idem_key: str, goal: str, *, approved: bool = False,
                max_calls: int = 1):
        if approved is not True:
            raise PermissionError("Queueing requires explicit authorization")
        if (not isinstance(idem_key, str) or not 1 <= len(idem_key) <= 120
                or not idem_key.strip() or not isinstance(goal, str)
                or not goal.strip() or len(goal) > 1200):
            raise ValueError("Invalid idempotency key or goal")
        if type(max_calls) is not int or not 1 <= max_calls <= 3:
            raise ValueError("Provider call budget must be between 1 and 3")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM authorized_jobs WHERE owner_key=? AND idem_key=?",
                             (self.owner_key, idem_key)).fetchone()
            if old:
                if old["goal"] != goal or old["max_calls"] != max_calls:
                    raise ValueError("Idempotency key conflict")
                return self._public(old)
            count = db.execute("SELECT COUNT(*) FROM authorized_jobs WHERE owner_key=?",
                               (self.owner_key,)).fetchone()[0]
            if count >= self.max_jobs:
                raise RuntimeError("Authorized job quota exceeded")
            task_id = uuid.uuid4().hex
            db.execute("INSERT INTO authorized_jobs (id,owner_key,idem_key,goal,state,max_calls) "
                       "VALUES(?,?,?,?,'queued',?)", (task_id, self.owner_key, idem_key, goal, max_calls))
            self._record(db, task_id, time.time(), "queued", "explicit_approval")
            row = db.execute("SELECT * FROM authorized_jobs WHERE id=?", (task_id,)).fetchone()
            return self._public(row)

    def get(self, task_id: str):
        with self._db() as db:
            row = db.execute("SELECT * FROM authorized_jobs WHERE owner_key=? AND id=?",
                             (self.owner_key, task_id)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._public(row)

    def list(self):
        with self._db() as db:
            rows = db.execute("SELECT * FROM authorized_jobs WHERE owner_key=? ORDER BY rowid",
                              (self.owner_key,)).fetchall()
        return [self._public(row) for row in rows]

    def events(self, task_id: str):
        self.get(task_id)
        with self._db() as db:
            return [dict(row) for row in db.execute(
                "SELECT event_id,at,state,code FROM authorized_job_events "
                "WHERE owner_key=? AND job_id=? ORDER BY event_id",
                (self.owner_key, task_id))]

    def claim(self, worker_id: str, *, approved: bool = False,
              now: float | None = None, lease_seconds: int = 60):
        if approved is not True:
            raise PermissionError("Claiming requires explicit authorization")
        if not isinstance(worker_id, str) or not 1 <= len(worker_id.strip()) <= 120:
            raise ValueError("Invalid worker identity")
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease duration")
        when = _finite_now(now)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM authorized_jobs WHERE owner_key=? AND state='queued' "
                "AND eligible_after<=? AND attempts<max_calls ORDER BY rowid LIMIT 1",
                (self.owner_key, when)).fetchone()
            if row is None:
                return None
            token = secrets.token_hex(16)
            db.execute("UPDATE authorized_jobs SET state='running', attempts=attempts+1, "
                       "worker_id=?, lease_token=?, lease_until=? WHERE id=? AND owner_key=?",
                       (worker_id, token, when + lease_seconds, row["id"], self.owner_key))
            self._record(db, row["id"], when, "running", "authorized_claim")
            result = self._public(db.execute("SELECT * FROM authorized_jobs WHERE id=?", (row["id"],)).fetchone())
            result["lease_token"] = token
            return result

    def _check_lease(self, db, task_id, token, when):
        row = db.execute("SELECT * FROM authorized_jobs WHERE owner_key=? AND id=?",
                         (self.owner_key, task_id)).fetchone()
        if row is None:
            raise KeyError(task_id)
        if (row["state"] != "running" or not isinstance(token, str)
                or not secrets.compare_digest(row["lease_token"] or "", token)
                or when >= row["lease_until"]):
            raise PermissionError("Work lease lost or expired")
        return row

    def complete(self, task_id, lease_token, draft, *, now: float | None = None):
        if not isinstance(draft, str) or not draft.strip():
            raise ValueError("Empty research draft")
        when = _finite_now(now)
        clean = draft.strip()[:12000]
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._check_lease(db, task_id, lease_token, when)
            db.execute("UPDATE authorized_jobs SET state='review_pending', "
                       "lease_token=NULL,lease_until=NULL,worker_id=NULL, "
                       "draft=?, result_digest=? WHERE owner_key=? AND id=?",
                       (clean, hashlib.sha256(clean.encode("utf-8")).hexdigest(), self.owner_key, task_id))
            self._record(db, task_id, when, "review_pending", "unverified_draft_saved")
        return {"id": task_id, "status": "review_pending", "draft": clean, "verified": False}

    def fail(self, task_id, lease_token, *, now: float | None = None):
        when = _finite_now(now)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._check_lease(db, task_id, lease_token, when)
            if row["attempts"] < row["max_calls"]:
                new_state = "queued"
                eligible = when + min(2 ** (row["attempts"] - 1), 60)
                code = "retry_requires_explicit_run"
                status = "retry_pending"
            else:
                new_state, eligible, code, status = "blocked", 0, "call_budget_exhausted", "blocked"
            db.execute("UPDATE authorized_jobs SET state=?, eligible_after=?, "
                       "lease_token=NULL, lease_until=NULL, worker_id=NULL "
                       "WHERE owner_key=? AND id=?",
                       (new_state, eligible, self.owner_key, task_id))
            self._record(db, task_id, when, new_state, code)
        return {"id": task_id, "status": status, "verified": False}

    def recover_expired(self, *, now: float | None = None):
        """Stop expired jobs; an external provider call may already have occurred."""
        when = _finite_now(now)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT id FROM authorized_jobs WHERE owner_key=? "
                              "AND state='running' AND lease_until<=?",
                              (self.owner_key, when)).fetchall()
            for row in rows:
                db.execute("UPDATE authorized_jobs SET state='blocked',lease_token=NULL, "
                           "lease_until=NULL,worker_id=NULL WHERE id=? AND owner_key=?",
                           (row["id"], self.owner_key))
                self._record(db, row["id"], when, "blocked", "lease_expired_manual_review")
        return len(rows)

    def run_once(self, worker_id: str, answer: Callable[[str], str], *,
                 approved: bool = False, now: float | None = None):
        """At most one provider call after explicit invocation; no background loop."""
        if approved is not True:
            raise PermissionError("Execution requires explicit authorization")
        if not callable(answer):
            raise ValueError("A callable authorized provider is required")
        job = self.claim(worker_id, approved=True, now=now)
        if job is None:
            return None
        try:
            draft = answer(job["goal"])
            if not isinstance(draft, str) or not draft.strip():
                raise ValueError("Empty provider draft")
            return self.complete(job["id"], job["lease_token"], draft, now=now)
        except Exception:
            # Never expose exception text: provider errors can contain tokens.
            return self.fail(job["id"], job["lease_token"], now=now)
