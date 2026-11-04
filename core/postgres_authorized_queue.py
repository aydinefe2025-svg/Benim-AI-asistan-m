"""Owner-scoped, bounded PostgreSQL task queue for authenticated CANO users.

This adapter is storage only. The caller must authenticate the owner and obtain
explicit approval before any queue claim. No background scheduler, model calls,
network traversal, or worker spawning is performed. Expired leases block rather
than replay work that may already have caused an external side effect.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
import uuid
from typing import Callable


class PostgresAuthorizedQueue:
    def __init__(self, database_url: str | None = None, *, owner_key: str,
                 max_jobs: int = 100, connect=None):
        self.database_url = database_url or os.environ.get("AGENT_TASK_DATABASE_URL")
        if not self.database_url:
            raise ValueError("AGENT_TASK_DATABASE_URL required")
        if not isinstance(owner_key, str) or not owner_key.strip() or len(owner_key) > 128:
            raise ValueError("Authenticated owner key required")
        if type(max_jobs) is not int or not 1 <= max_jobs <= 1000:
            raise ValueError("Invalid bounded job quota")
        self.owner_key = owner_key
        self.max_jobs = max_jobs
        self._connect = connect

    def _db(self):
        if self._connect:
            return self._connect(self.database_url, connect_timeout=8)
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.database_url, connect_timeout=8, row_factory=dict_row)

    def verify_schema(self):
        """Validate pre-provisioned queue tables and privileges with SELECT only."""
        with self._db() as db, db.cursor() as cur:
            cur.execute(
                "SELECT owner_key,id,idem_key,goal,state,max_calls,attempts,"
                "eligible_after,lease_token,worker_id,lease_until,result_digest,draft,created_at "
                "FROM public.cano_authorized_jobs LIMIT 0"
            )
            cur.execute(
                "SELECT event_id,owner_key,job_id,at,state,code "
                "FROM public.cano_authorized_job_events LIMIT 0"
            )
            cur.execute("""SELECT
                has_table_privilege(current_user,
                    'public.cano_authorized_jobs', 'SELECT') AS jobs_select,
                has_table_privilege(current_user,
                    'public.cano_authorized_jobs', 'INSERT') AS jobs_insert,
                has_table_privilege(current_user,
                    'public.cano_authorized_jobs', 'UPDATE') AS jobs_update,
                has_table_privilege(current_user,
                    'public.cano_authorized_job_events', 'SELECT') AS events_select,
                has_table_privilege(current_user,
                    'public.cano_authorized_job_events', 'INSERT') AS events_insert,
                has_sequence_privilege(current_user,
                    'public.cano_authorized_job_events_event_id_seq', 'USAGE') AS events_seq_usage
            """)
            privileges = cur.fetchone()
            if not privileges or not all(privileges.values()):
                raise PermissionError("authorized queue runtime privileges are incomplete")


    @staticmethod
    def _public(row):
        if row is None:
            return None
        output = dict(row)
        output.pop("owner_key", None)
        output.pop("lease_token", None)
        return output

    def _event(self, cur, job_id, when, state, code):
        cur.execute("INSERT INTO cano_authorized_job_events "
                    "(owner_key,job_id,at,state,code) VALUES(%s,%s,%s,%s,%s)",
                    (self.owner_key, job_id, when, state, code))

    def enqueue(self, idem_key: str, goal: str, *, approved: bool = False,
                max_calls: int = 1):
        if approved is not True:
            raise PermissionError("Explicit authorization required")
        if (not isinstance(idem_key, str) or not 1 <= len(idem_key) <= 120
                or not idem_key.strip() or not isinstance(goal, str)
                or not goal.strip() or len(goal) > 1200):
            raise ValueError("Invalid idempotency key or goal")
        if type(max_calls) is not int or not 1 <= max_calls <= 3:
            raise ValueError("Call budget must be between 1 and 3")
        with self._db() as db, db.cursor() as cur:
            # Serializes a single owner's quota and idempotent enqueue even
            # across multiple distinct hosts and connections.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s)::bigint)",
                        ("cano-authorized:" + self.owner_key,))
            cur.execute("SELECT * FROM cano_authorized_jobs "
                        "WHERE owner_key=%s AND idem_key=%s",
                        (self.owner_key, idem_key))
            prior = cur.fetchone()
            if prior:
                if prior["goal"] != goal or prior["max_calls"] != max_calls:
                    raise ValueError("Idempotency key conflict")
                return self._public(prior)
            cur.execute("SELECT COUNT(*) AS n FROM cano_authorized_jobs WHERE owner_key=%s",
                        (self.owner_key,))
            if cur.fetchone()["n"] >= self.max_jobs:
                raise RuntimeError("Authorized queue quota reached")
            job_id, when = uuid.uuid4().hex, time.time()
            cur.execute("INSERT INTO cano_authorized_jobs "
                        "(owner_key,id,idem_key,goal,state,max_calls,created_at) "
                        "VALUES(%s,%s,%s,%s,'queued',%s,%s)",
                        (self.owner_key, job_id, idem_key, goal, max_calls, when))
            self._event(cur, job_id, when, "queued", "explicit_approval")
            cur.execute("SELECT * FROM cano_authorized_jobs "
                        "WHERE owner_key=%s AND id=%s",
                        (self.owner_key, job_id))
            return self._public(cur.fetchone())

    def get(self, task_id: str):
        with self._db() as db, db.cursor() as cur:
            cur.execute("SELECT * FROM cano_authorized_jobs "
                        "WHERE owner_key=%s AND id=%s",
                        (self.owner_key, task_id))
            row = cur.fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._public(row)

    def list(self):
        with self._db() as db, db.cursor() as cur:
            cur.execute("SELECT * FROM cano_authorized_jobs WHERE owner_key=%s "
                        "ORDER BY created_at,id", (self.owner_key,))
            return [self._public(row) for row in cur.fetchall()]

    def events(self, task_id: str):
        self.get(task_id)
        with self._db() as db, db.cursor() as cur:
            cur.execute("SELECT event_id,at,state,code FROM cano_authorized_job_events "
                        "WHERE owner_key=%s AND job_id=%s ORDER BY event_id",
                        (self.owner_key, task_id))
            return list(cur.fetchall())

    def claim(self, worker_id: str, *, approved: bool = False,
              now: float | None = None, lease_seconds: int = 60):
        if approved is not True:
            raise PermissionError("Explicit execution authorization required")
        if not isinstance(worker_id, str) or not 1 <= len(worker_id.strip()) <= 120:
            raise ValueError("Invalid worker identity")
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease duration")
        when = time.time() if now is None else float(now)
        with self._db() as db, db.cursor() as cur:
            cur.execute("SELECT * FROM cano_authorized_jobs "
                        "WHERE owner_key=%s AND state='queued' AND eligible_after<=%s "
                        "AND attempts<max_calls ORDER BY created_at,id "
                        "FOR UPDATE SKIP LOCKED LIMIT 1",
                        (self.owner_key, when))
            row = cur.fetchone()
            if row is None:
                return None
            token = secrets.token_hex(16)
            cur.execute("UPDATE cano_authorized_jobs "
                        "SET state='running', attempts=attempts+1, "
                        "worker_id=%s,lease_token=%s,lease_until=%s "
                        "WHERE owner_key=%s AND id=%s",
                        (worker_id, token, when + lease_seconds, self.owner_key, row["id"]))
            self._event(cur, row["id"], when, "running", "authorized_claim")
            cur.execute("SELECT * FROM cano_authorized_jobs WHERE owner_key=%s AND id=%s",
                        (self.owner_key, row["id"]))
            output = self._public(cur.fetchone())
            output["lease_token"] = token
            return output

    def _require_lease(self, cur, task_id, token, when):
        cur.execute("SELECT * FROM cano_authorized_jobs WHERE owner_key=%s AND id=%s "
                    "FOR UPDATE", (self.owner_key, task_id))
        row = cur.fetchone()
        if row is None:
            raise KeyError(task_id)
        if (row["state"] != "running" or not isinstance(token, str)
                or not secrets.compare_digest(row["lease_token"] or "", token)
                or row["lease_until"] is None or when > row["lease_until"]):
            raise PermissionError("Job lease expired or lost")
        return row

    def complete(self, task_id, lease_token, draft, *, now: float | None = None):
        if not isinstance(draft, str) or not draft.strip():
            raise ValueError("Empty research draft")
        when = time.time() if now is None else float(now)
        clean = draft.strip()[:12000]
        with self._db() as db, db.cursor() as cur:
            self._require_lease(cur, task_id, lease_token, when)
            cur.execute("UPDATE cano_authorized_jobs "
                        "SET state='review_pending',lease_token=NULL,worker_id=NULL,"
                        "lease_until=NULL,draft=%s,result_digest=%s "
                        "WHERE owner_key=%s AND id=%s",
                        (clean, hashlib.sha256(clean.encode("utf-8")).hexdigest(),
                         self.owner_key, task_id))
            self._event(cur, task_id, when, "review_pending", "unverified_draft_saved")
        return {"id": task_id, "status": "review_pending",
                "draft": clean, "verified": False}

    def fail(self, task_id, lease_token, *, now: float | None = None):
        when = time.time() if now is None else float(now)
        with self._db() as db, db.cursor() as cur:
            row = self._require_lease(cur, task_id, lease_token, when)
            if row["attempts"] < row["max_calls"]:
                state, eligible, code, outcome = (
                    "queued", when + min(2 ** (row["attempts"] - 1), 60),
                    "retry_requires_explicit_run", "retry_pending")
            else:
                state, eligible, code, outcome = (
                    "blocked", 0, "call_budget_exhausted", "blocked")
            cur.execute("UPDATE cano_authorized_jobs "
                        "SET state=%s,eligible_after=%s,lease_token=NULL,"
                        "worker_id=NULL,lease_until=NULL "
                        "WHERE owner_key=%s AND id=%s",
                        (state, eligible, self.owner_key, task_id))
            self._event(cur, task_id, when, state, code)
        return {"id": task_id, "status": outcome, "verified": False}

    def recover_expired(self, *, now: float | None = None):
        """Block expired work; external side effects must never be replayed blindly."""
        when = time.time() if now is None else float(now)
        with self._db() as db, db.cursor() as cur:
            cur.execute("SELECT id FROM cano_authorized_jobs "
                        "WHERE owner_key=%s AND state='running' AND lease_until<%s "
                        "FOR UPDATE SKIP LOCKED", (self.owner_key, when))
            rows = cur.fetchall()
            for row in rows:
                cur.execute("UPDATE cano_authorized_jobs SET state='blocked',"
                            "lease_token=NULL,worker_id=NULL,lease_until=NULL "
                            "WHERE owner_key=%s AND id=%s", (self.owner_key, row["id"]))
                self._event(cur, row["id"], when, "blocked",
                            "lease_expired_manual_review")
            return len(rows)

    def run_once(self, worker_id: str, answer: Callable[[str], str], *,
                 approved: bool = False, now: float | None = None):
        """One explicitly triggered provider attempt; no automatic background calls."""
        if approved is not True:
            raise PermissionError("Explicit execution authorization required")
        if not callable(answer):
            raise ValueError("An authorized provider callback is required")
        job = self.claim(worker_id, approved=True, now=now)
        if job is None:
            return None
        try:
            draft = answer(job["goal"])
            if not isinstance(draft, str) or not draft.strip():
                raise ValueError("Empty provider result")
            return self.complete(job["id"], job["lease_token"], draft, now=now)
        except Exception:
            # Never log provider errors: they can contain credentials or prompts.
            return self.fail(job["id"], job["lease_token"], now=now)
