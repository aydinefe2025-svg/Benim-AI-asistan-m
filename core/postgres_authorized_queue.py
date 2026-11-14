"""Owner-scoped, bounded PostgreSQL task queue for authenticated CANO users.

This adapter is storage only. The caller must authenticate the owner and obtain
explicit approval before any queue claim. No background scheduler, model calls,
network traversal, or worker spawning is performed. Expired leases block rather
than replay work that may already have caused an external side effect.
"""
from __future__ import annotations

import hashlib
import math
import logging
import logging
import os
import secrets
import threading
import time
import uuid
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


class PostgresAuthorizedQueue:
    def __init__(self, database_url: str | None = None, *, owner_key: str,
                 max_jobs: int = 100, connect=None, allow_test_clock: bool = False):
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
        # Only disposable integration tests may simulate a clock. Never enable
        # this escape hatch in an authenticated production queue.
        if type(allow_test_clock) is not bool:
            raise ValueError("allow_test_clock must be boolean")
        self._allow_test_clock = allow_test_clock

    def _override(self, now):
        """Explicit clocks are for isolated test databases only."""
        if now is None:
            return None
        validated = _finite_now(now)
        if not self._allow_test_clock:
            raise PermissionError("Clock overrides require isolated test configuration")
        return validated

    @staticmethod
    def _server_clock(cur):
        """Read the authority clock from PostgreSQL inside the current transaction."""
        cur.execute("SELECT EXTRACT(EPOCH FROM clock_timestamp()) AS cano_now")
        row = cur.fetchone()
        if not isinstance(row, dict) or "cano_now" not in row:
            raise RuntimeError("PostgreSQL server clock unavailable")
        return _finite_now(row["cano_now"])

    def _db(self):
        if self._connect:
            return self._connect(self.database_url, connect_timeout=8)
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.database_url, connect_timeout=8, row_factory=dict_row)

    def verify_schema(self):
        """Validate pre-provisioned queue tables and privileges with SELECT only."""
        stage = "connect"
        try:
            with self._db() as db, db.cursor() as cur:
                stage = "identity"
                cur.execute("""SELECT current_user AS runtime_role,
                    current_database() AS runtime_database,
                    has_table_privilege(current_user,
                        'public.cano_authorized_jobs', 'SELECT') AS queue_select""")
                identity = cur.fetchone() or {}
                logging.getLogger(__name__).info(
                    "Authorized queue DB identity role=%s database=%s queue_select=%s",
                    identity.get("runtime_role"), identity.get("runtime_database"),
                    identity.get("queue_select"),
                )
                stage = "jobs_columns"
                cur.execute(
                    "SELECT owner_key,id,idem_key,goal,state,max_calls,attempts,"
                    "eligible_after,lease_token,worker_id,lease_until,result_digest,draft,created_at "
                    "FROM public.cano_authorized_jobs LIMIT 0"
                )
                stage = "events_columns"
                cur.execute(
                    "SELECT event_id,owner_key,job_id,at,state,code "
                    "FROM public.cano_authorized_job_events LIMIT 0"
                )
                stage = "privileges"
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
        except Exception as exc:
            # Log only a fixed stage label, SQLSTATE, and class; no SQL or credentials.
            logging.getLogger(__name__).warning(
                "Authorized queue schema verification failed at %s (%s, SQLSTATE=%s)",
                stage, type(exc).__name__, getattr(exc, "sqlstate", None),
            )
            raise


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
        when = self._override(now)
        with self._db() as db, db.cursor() as cur:
            if when is None:
                when = self._server_clock(cur)
            cur.execute("SELECT * FROM cano_authorized_jobs "
                        "WHERE owner_key=%s AND state='queued' AND eligible_after<=%s "
                        "AND attempts<max_calls ORDER BY created_at,id "
                        "FOR UPDATE SKIP LOCKED LIMIT 1",
                        (self.owner_key, when))
            row = cur.fetchone()
            if row is None:
                return None
            # Lock is held; refresh the server timestamp after the claim query.
            if now is None:
                when = self._server_clock(cur)
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
        # Re-read *after* locking the row. The worker wall clock cannot
        # grant a stale worker a lease or prolong an existing one.
        checked_at = self._server_clock(cur) if when is None else when
        if (row["state"] != "running" or not isinstance(token, str)
                or not secrets.compare_digest(row["lease_token"] or "", token)
                or row["lease_until"] is None or checked_at >= row["lease_until"]):
            raise PermissionError("Job lease expired or lost")
        return row, checked_at

    def complete(self, task_id, lease_token, draft, *, now: float | None = None):
        if not isinstance(draft, str) or not draft.strip():
            raise ValueError("Empty research draft")
        when = self._override(now)
        clean = draft.strip()[:12000]
        with self._db() as db, db.cursor() as cur:
            _, when = self._require_lease(cur, task_id, lease_token, when)
            cur.execute("UPDATE cano_authorized_jobs "
                        "SET state='review_pending',lease_token=NULL,worker_id=NULL,"
                        "lease_until=NULL,draft=%s,result_digest=%s "
                        "WHERE owner_key=%s AND id=%s",
                        (clean, hashlib.sha256(clean.encode("utf-8")).hexdigest(),
                         self.owner_key, task_id))
            self._event(cur, task_id, when, "review_pending", "unverified_draft_saved")
        return {"id": task_id, "status": "review_pending",
                "draft": clean, "verified": False}

    def renew_lease(self, task_id, lease_token, *, lease_seconds: int = 60):
        """Extend a live lease under its row lock; an expired lease is never revived."""
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease duration")
        with self._db() as db, db.cursor() as cur:
            self._require_lease(cur, task_id, lease_token, None)
            # Keep the expiry predicate in the write as well as the locked read:
            # the server clock is authoritative even at the expiry boundary.
            cur.execute("UPDATE cano_authorized_jobs SET lease_until="
                        "EXTRACT(EPOCH FROM clock_timestamp())+%s "
                        "WHERE owner_key=%s AND id=%s AND state='running' "
                        "AND lease_token=%s AND lease_until>EXTRACT(EPOCH FROM clock_timestamp())",
                        (lease_seconds, self.owner_key, task_id, lease_token))
            if cur.rowcount != 1:
                raise PermissionError("Job lease expired or lost")
        return True

    def fail(self, task_id, lease_token, *, now: float | None = None):
        when = self._override(now)
        with self._db() as db, db.cursor() as cur:
            row, when = self._require_lease(cur, task_id, lease_token, when)
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
        when = self._override(now)
        with self._db() as db, db.cursor() as cur:
            if when is None:
                # Evaluate expiry at the server, never from a client clock.
                cur.execute("SELECT id FROM cano_authorized_jobs "
                            "WHERE owner_key=%s AND state='running' "
                            "AND lease_until<=EXTRACT(EPOCH FROM clock_timestamp()) "
                            "FOR UPDATE SKIP LOCKED", (self.owner_key,))
                rows = cur.fetchall()
                when = self._server_clock(cur)
            else:
                cur.execute("SELECT id FROM cano_authorized_jobs "
                            "WHERE owner_key=%s AND state='running' AND lease_until<=%s "
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
                 approved: bool = False, now: float | None = None,
                 lease_seconds: int = 60):
        """One explicitly triggered provider attempt; no automatic background calls."""
        if approved is not True:
            raise PermissionError("Explicit execution authorization required")
        if not callable(answer):
            raise ValueError("An authorized provider callback is required")
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease duration")
        job = self.claim(worker_id, approved=True, now=now, lease_seconds=lease_seconds)
        if job is None:
            return None
        stopped, lost = threading.Event(), threading.Event()
        interval = min(10.0, max(.25, lease_seconds / 3))

        def heartbeat():
            while not stopped.wait(interval):
                try:
                    self.renew_lease(job["id"], job["lease_token"],
                                     lease_seconds=lease_seconds)
                except Exception:
                    # No exception details: they can include connection data.
                    lost.set()
                    return

        def persist_failure():
            """A failed provider attempt may already have cost an external call.

            If recording its failure is unacknowledged, never promise a retry:
            the database may have committed the failure transition already.
            """
            try:
                return self.fail(job["id"], job["lease_token"], now=now)
            except PermissionError:
                return {"id": job["id"], "status": "lease_lost", "verified": False}
            except Exception:
                # Driver exceptions may contain secrets; no details cross this boundary.
                return {"id": job["id"], "status": "failure_uncertain",
                        "manual_review": True, "verified": False}

        thread = threading.Thread(target=heartbeat, name="cano-queue-lease-heartbeat", daemon=True)
        thread.start()
        try:
            try:
                draft = answer(job["goal"])
            except Exception:
                # Never log provider errors: they can contain credentials or prompts.
                if lost.is_set():
                    return {"id": job["id"], "status": "lease_lost", "verified": False}
                return persist_failure()
            if lost.is_set():
                return {"id": job["id"], "status": "lease_lost", "verified": False}
            if not isinstance(draft, str) or not draft.strip():
                return persist_failure()
            try:
                return self.complete(job["id"], job["lease_token"], draft, now=now)
            except PermissionError:
                return {"id": job["id"], "status": "lease_lost", "verified": False}
            except Exception:
                # The transaction may have committed before its acknowledgement was
                # lost. Leave reconciliation to recovery/manual review; never retry.
                return {"id": job["id"], "status": "completion_uncertain",
                        "manual_review": True, "verified": False}
        finally:
            stopped.set()
            # A PostgreSQL connection is bounded by connect_timeout=8; never
            # make callback completion wait indefinitely for a stuck renewal.
            thread.join(timeout=8.5)
