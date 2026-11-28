"""Durable one-task capability over the existing PostgreSQL lease.

Server-side only. Issuance and revocation require an authenticated owner
queue supplied by the caller; never construct that owner from worker input.
Worker credentials are random, hashed at rest, limited to a single job,
and expire with the existing server-clock lease. No new schema or DB
credential is distributed. A lost response is manual-review territory,
not permission to repeat inference. This module does not expose an HTTP API.
"""
from core.postgres_owner_proof import set_owner_context

import hashlib
import re
import secrets
from core.local_task_handoff import TICKET_SCHEMA, validate_ticket, _validate_result, _json, _hash
from core.postgres_authorized_queue import PostgresAuthorizedQueue

_READY = "local-http-ready:"
_TAKEN = "local-http-taken:"
_TOKEN_RE = re.compile(r"([0-9a-f]{32})\.([0-9a-f]{64})")


class PostgresLocalGrant:
    def __init__(self, database_url, *, connect=None):
        self.database_url = database_url
        self._connect = connect

    def _db(self):
        if self._connect is not None:
            return self._connect(self.database_url, connect_timeout=8)
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.database_url, connect_timeout=8, row_factory=dict_row)

    @staticmethod
    def issue(queue, *, approved=False):
        if approved is not True:
            raise PermissionError("Explicit owner authorization required")
        secret = secrets.token_hex(32)
        digest = hashlib.sha256(secret.encode("ascii")).hexdigest()
        row = queue.claim(_READY+digest, approved=True, lease_seconds=3600)
        if row is None:
            return None
        if not re.fullmatch("[0-9a-f]{32}", row["id"]):
            raise RuntimeError("Unexpected queue identity; manual review required")
        return {"id": row["id"], "grant": row["id"]+"."+secret,
                "expires_at": float(row["lease_until"])}

    @staticmethod
    def _parts(token):
        if not isinstance(token, str) or len(token) != 97:
            raise PermissionError("Invalid grant")
        match = _TOKEN_RE.fullmatch(token)
        if not match:
            raise PermissionError("Invalid grant")
        return match[1], hashlib.sha256(match[2].encode("ascii")).hexdigest()

    @staticmethod
    def _ticket(row, digest):
        body = {"schema": TICKET_SCHEMA, "job_id": row["id"],
                "nonce": digest[:32], "goal": row["goal"],
                "expires_at": float(row["lease_until"])}
        body["ticket_sha256"] = _hash(_json(body))
        return validate_ticket(body)

    @staticmethod
    def _locked(cur, job_id, worker):
        # An exact id + unguessable capability hash is the only worker lookup.
        # Never accept an owner key or arbitrary job id as worker authority.
        # Legacy databases without active RLS retain the existing exact
        # capability lookup. An RLS database must provision the narrow
        # resolver; missing resolver or denied capability fails closed.
        cur.execute("SELECT pg_catalog.row_security_active("
                    "'public.cano_authorized_jobs'::regclass) AS rls_active")
        if cur.fetchone()["rls_active"]:
            cur.execute("SELECT public.cano_resolve_local_grant_owner(%s,%s) AS owner_key",
                        (job_id, worker))
            owner = cur.fetchone()["owner_key"]
            if not owner:
                raise PermissionError("Grant unavailable")
            set_owner_context(cur, owner)
        cur.execute("SELECT * FROM public.cano_authorized_jobs "
                    "WHERE id=%s AND worker_id=%s AND state='running' FOR UPDATE",
                    (job_id, worker))
        rows = cur.fetchall()
        if len(rows) != 1:
            raise PermissionError("Grant unavailable")
        row = rows[0]
        now = PostgresAuthorizedQueue._server_clock(cur)
        if (not row.get("lease_token") or row.get("lease_until") is None
                or now >= row["lease_until"]):
            raise PermissionError("Grant expired")
        return row, now

    @staticmethod
    def _event(cur, row, now, state, code):
        cur.execute("INSERT INTO public.cano_authorized_job_events "
                    "(owner_key,job_id,at,state,code) VALUES(%s,%s,%s,%s,%s)",
                    (row["owner_key"], row["id"], now, state, code))

    def take(self, token):
        job_id, digest = self._parts(token)
        with self._db() as db, db.cursor() as cur:
            row, now = self._locked(cur, job_id, _READY+digest)
            ticket = self._ticket(row, digest)
            cur.execute("UPDATE public.cano_authorized_jobs SET worker_id=%s "
                        "WHERE owner_key=%s AND id=%s AND worker_id=%s "
                        "AND state='running' AND lease_until>EXTRACT(EPOCH FROM clock_timestamp())",
                        (_TAKEN+digest, row["owner_key"], job_id, _READY+digest))
            if cur.rowcount != 1:
                raise PermissionError("Grant expired or unavailable")
            self._event(cur, row, now, "running", "local_http_taken")
        return ticket

    def finish(self, token, result):
        job_id, digest = self._parts(token)
        with self._db() as db, db.cursor() as cur:
            row, now = self._locked(cur, job_id, _TAKEN+digest)
            _validate_result(self._ticket(row, digest), result)
            cur.execute("UPDATE public.cano_authorized_jobs SET state='review_pending', "
                        "lease_token=NULL,worker_id=NULL,lease_until=NULL,draft=%s,result_digest=%s "
                        "WHERE owner_key=%s AND id=%s AND worker_id=%s AND state='running' "
                        "AND lease_until>EXTRACT(EPOCH FROM clock_timestamp())",
                        (result["draft"],result["draft_sha256"],row["owner_key"],job_id,_TAKEN+digest))
            if cur.rowcount != 1:
                raise PermissionError("Grant expired or unavailable")
            self._event(cur, row, now, "review_pending", "unverified_draft_saved")
        # Read after commit, with a new owner-scoped connection. A lost ack
        # does not authorize a repeat; the capability is now consumed.
        q = PostgresAuthorizedQueue(self.database_url, owner_key=row["owner_key"],
                                    connect=self._connect)
        saved = q.get(job_id)
        if (saved["state"] != "review_pending" or saved["draft"] != result["draft"]
                or saved["result_digest"] != result["draft_sha256"]):
            raise RuntimeError("Commit readback uncertain; do not rerun")
        return {"id":job_id, "status":"review_pending","verified":False,"readback":True}

    @staticmethod
    def revoke(queue, job_id, *, approved=False):
        if approved is not True:
            raise PermissionError("Explicit authenticated owner revocation required")
        if not isinstance(job_id,str) or not re.fullmatch("[0-9a-f]{32}",job_id):
            raise ValueError("Invalid job id")
        with queue._db() as db, db.cursor() as cur:
            set_owner_context(cur, queue.owner_key)
            cur.execute("SELECT * FROM public.cano_authorized_jobs "
                        "WHERE owner_key=%s AND id=%s AND state='running' FOR UPDATE",
                        (queue.owner_key,job_id))
            row=cur.fetchone()
            if not row or not (row.get("worker_id") or "").startswith((_READY,_TAKEN)):
                raise PermissionError("No revocable local grant")
            now=PostgresAuthorizedQueue._server_clock(cur)
            cur.execute("UPDATE public.cano_authorized_jobs SET state='blocked',"
                        "lease_token=NULL,worker_id=NULL,lease_until=NULL "
                        "WHERE owner_key=%s AND id=%s AND state='running'",
                        (queue.owner_key,job_id))
            if cur.rowcount != 1:
                raise PermissionError("Grant unavailable")
            PostgresLocalGrant._event(cur,row,now,"blocked","local_http_revoked")
        return {"id":job_id,"status":"blocked","verified":False}
