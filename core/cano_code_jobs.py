"""Authenticated owner-scoped development request queue for CANO web chat.

This module only persists a bounded request. It NEVER edits a repository,
runs shell commands, deploys or handles GitHub credentials.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata


MAX_ACTIVE_JOBS = 3
ALLOWED_PREFIXES = frozenset(("cano kod", "cano gelistir", "cano yazilim"))


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).replace("ı", "i")


def parse_code_request(message):
    """Opt-in code execution request; ordinary chat and research remain unchanged."""
    if not isinstance(message, str):
        return None
    head, sep, goal = message.strip().partition(":")
    if not sep or _normalize(head).strip() not in ALLOWED_PREFIXES:
        return None
    goal = goal.strip()
    if not 8 <= len(goal) <= 1200 or "\x00" in goal:
        raise ValueError("Development goal must be 8–1200 characters")
    if re.search(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{16,}|postgres(?:ql)?://|-----BEGIN [A-Z ]+PRIVATE KEY)", goal, re.I):
        raise ValueError("Do not submit credentials in CANO development requests")
    return goal


class CodeJobStore:
    """Restricted agent_task_app SELECT/INSERT via per-transaction owner RLS."""

    def __init__(self, database_url, owner_key, *, connect=None):
        if not isinstance(database_url, str) or not database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("AGENT_TASK_DATABASE_URL must be PostgreSQL")
        if not isinstance(owner_key, str) or not re.fullmatch(r"oidc_[0-9a-f]{64}", owner_key):
            raise PermissionError("Verified OIDC owner key required")
        self.database_url = database_url
        self.owner_key = owner_key
        self._connect = connect

    def _db(self):
        if self._connect is not None:
            return self._connect(self.database_url)
        import psycopg
        return psycopg.connect(self.database_url, connect_timeout=8)

    def _scope(self, cursor):
        cursor.execute("SELECT set_config('cano.owner_key', %s, true)", (self.owner_key,))

    def verify_schema(self):
        with self._db() as conn, conn.cursor() as cur:
            self._scope(cur)
            cur.execute(
                "SELECT id,owner_key,goal_hash,goal,status,pr_url,deploy_id,reason_code "
                "FROM public.cano_code_jobs LIMIT 0"
            )

    def enqueue(self, goal):
        if not isinstance(goal, str) or not 8 <= len(goal.strip()) <= 1200:
            raise ValueError("Invalid development goal")
        goal = goal.strip()
        if parse_code_request("CANO kod: " + goal) is None:
            raise ValueError("Invalid development request")
        digest = hashlib.sha256(_normalize(goal).encode("utf-8")).hexdigest()
        with self._db() as conn, conn.cursor() as cur:
            self._scope(cur)
            # Serialize an owner's submissions across web sessions and workers.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s)::bigint)",
                        ("cano-code:" + self.owner_key,))
            cur.execute(
                "SELECT id::text,status FROM public.cano_code_jobs "
                "WHERE owner_key=%s AND goal_hash=%s",
                (self.owner_key, digest),
            )
            prior = cur.fetchone()
            if prior:
                return {"id": prior[0], "status": prior[1], "duplicate": True}
            cur.execute(
                "SELECT COUNT(*) FROM public.cano_code_jobs WHERE owner_key=%s "
                "AND status IN ('queued','running','pr_open','ci_verified')",
                (self.owner_key,),
            )
            if cur.fetchone()[0] >= MAX_ACTIVE_JOBS:
                raise RuntimeError("CANO development queue is at its active-job limit")
            cur.execute(
                "INSERT INTO public.cano_code_jobs(owner_key,goal_hash,goal) "
                "VALUES(%s,%s,%s) ON CONFLICT (owner_key,goal_hash) DO NOTHING "
                "RETURNING id::text,status",
                (self.owner_key, digest, goal),
            )
            result = cur.fetchone()
            if result is None:
                cur.execute(
                    "SELECT id::text,status FROM public.cano_code_jobs "
                    "WHERE owner_key=%s AND goal_hash=%s",
                    (self.owner_key, digest),
                )
                result = cur.fetchone()
            if not result:
                raise RuntimeError("No committed CANO development queue receipt")
        return {"id": result[0], "status": result[1], "duplicate": False}

    def recent(self, limit=8):
        if type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError("Invalid queue listing limit")
        with self._db() as conn, conn.cursor() as cur:
            self._scope(cur)
            cur.execute(
                "SELECT id::text,status,left(goal,100),COALESCE(pr_url,''),"
                "COALESCE(deploy_id,''),COALESCE(reason_code,'') "
                "FROM public.cano_code_jobs WHERE owner_key=%s "
                "ORDER BY created_at DESC,id DESC LIMIT %s",
                (self.owner_key, limit),
            )
            result = cur.fetchall()
        return [
            {"id": row[0], "status": row[1], "goal": row[2], "pr_url": row[3],
             "deploy_id": row[4], "reason_code": row[5]}
            for row in result
        ]
