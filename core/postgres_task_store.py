"""Authenticated, owner-scoped PostgreSQL task and draft storage.

The database URL is read only at runtime. Every data query is scoped to an
opaque OIDC owner key; imports preserve old content only as untrusted audit
provenance and never restore a verified status.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from core.task_store import ALLOWED_TRANSITIONS, STATUSES


class DatabaseNotConfigured(RuntimeError):
    pass


_COLUMNS = "id,title,goal,status,evidence,blockers,created_at,updated_at"


def _iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _decode_task(row: Any) -> dict[str, Any]:
    item = dict(zip(_COLUMNS.split(","), row))
    item["evidence"] = json.loads(item["evidence"] or "[]")
    item["blockers"] = json.loads(item["blockers"] or "[]")
    item["created_at"] = _iso(item["created_at"])
    item["updated_at"] = _iso(item["updated_at"])
    return item


class PostgresTaskStore:
    def __init__(self, database_url: str | None = None, owner_key: str = "", *, connect=None):
        self.database_url = database_url or os.environ.get("AGENT_TASK_DATABASE_URL")
        if not self.database_url:
            raise DatabaseNotConfigured("AGENT_TASK_DATABASE_URL is required")
        if not isinstance(owner_key, str) or not owner_key.strip() or len(owner_key) > 128:
            raise ValueError("authenticated owner_key is required")
        self.owner_key = owner_key
        if connect is None:
            import psycopg
            connect = psycopg.connect
        self._connect = connect

    def _connection(self):
        return self._connect(self.database_url, connect_timeout=8)

    def initialize(self) -> None:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_research_tasks (
                    owner_key TEXT NOT NULL,
                    id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    goal TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN
                        ('planned','running','blocked','done','verified','failed','review_pending')),
                    evidence TEXT NOT NULL DEFAULT '[]',
                    blockers TEXT NOT NULL DEFAULT '[]',
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY(owner_key,id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_research_task_events (
                    event_id BIGSERIAL PRIMARY KEY,
                    owner_key TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    at TIMESTAMPTZ NOT NULL,
                    old_status TEXT,
                    new_status TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(owner_key,task_id)
                        REFERENCES agent_research_tasks(owner_key,id) ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_research_drafts (
                    owner_key TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY(owner_key,task_id),
                    FOREIGN KEY(owner_key,task_id)
                        REFERENCES agent_research_tasks(owner_key,id) ON DELETE CASCADE
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_research_tasks_owner_status
                ON agent_research_tasks(owner_key,status,created_at)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_research_events_owner_task
                ON agent_research_task_events(owner_key,task_id,event_id)
            """)

    def create(self, title: str, goal: str = "") -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("Task title cannot be empty")
        task_id, now = str(uuid.uuid4()), datetime.now(timezone.utc)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(f"""INSERT INTO agent_research_tasks
                (owner_key,id,title,goal,status,created_at,updated_at)
                VALUES (%s,%s,%s,%s,'planned',%s,%s)""",
                (self.owner_key, task_id, title, goal.strip(), now, now))
            cur.execute("""INSERT INTO agent_research_task_events
                (owner_key,task_id,at,old_status,new_status,note)
                VALUES (%s,%s,%s,NULL,'planned','Task created')""",
                (self.owner_key, task_id, now))
        return self.get(task_id)

    def _select_one(self, cur, task_id: str):
        cur.execute(f"SELECT {_COLUMNS} FROM agent_research_tasks WHERE owner_key=%s AND id=%s",
                    (self.owner_key, task_id))
        return cur.fetchone()

    def get(self, task_id: str) -> dict[str, Any]:
        with self._connection() as conn, conn.cursor() as cur:
            row = self._select_one(cur, task_id)
        if row is None:
            raise KeyError(f"Unknown task: {task_id}")
        return _decode_task(row)

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        if status is not None and status not in STATUSES:
            raise ValueError(f"Invalid status: {status}")
        with self._connection() as conn, conn.cursor() as cur:
            if status:
                cur.execute(f"SELECT {_COLUMNS} FROM agent_research_tasks "
                            "WHERE owner_key=%s AND status=%s ORDER BY created_at,id",
                            (self.owner_key, status))
            else:
                cur.execute(f"SELECT {_COLUMNS} FROM agent_research_tasks "
                            "WHERE owner_key=%s ORDER BY created_at,id", (self.owner_key,))
            rows = cur.fetchall()
        return [_decode_task(row) for row in rows]

    def transition(self, task_id: str, status: str, *, note: str = "",
                   evidence: list[str] | None = None,
                   blockers: list[str] | None = None) -> dict[str, Any]:
        if status not in STATUSES:
            raise ValueError(f"Invalid task status: {status}")
        if status == "verified":
            raise ValueError("Verified status requires independent evidence review")
        now = datetime.now(timezone.utc)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT status,evidence,blockers FROM agent_research_tasks
                WHERE owner_key=%s AND id=%s FOR UPDATE""", (self.owner_key, task_id))
            row = cur.fetchone()
            if row is None:
                raise KeyError(f"Unknown task: {task_id}")
            old_status, raw_evidence, raw_blockers = row
            if status not in ALLOWED_TRANSITIONS[old_status]:
                raise ValueError(f"Invalid task transition: {old_status} -> {status}")
            prior_evidence = json.loads(raw_evidence or "[]")
            new_evidence = prior_evidence + [item.strip() for item in (evidence or [])
                                               if isinstance(item, str) and item.strip()]
            new_blockers = blockers if blockers is not None else json.loads(raw_blockers or "[]")
            cur.execute("""UPDATE agent_research_tasks SET status=%s,evidence=%s,
                blockers=%s,updated_at=%s WHERE owner_key=%s AND id=%s""",
                (status, json.dumps(new_evidence, ensure_ascii=False),
                 json.dumps(new_blockers, ensure_ascii=False), now, self.owner_key, task_id))
            cur.execute("""INSERT INTO agent_research_task_events
                (owner_key,task_id,at,old_status,new_status,note)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (self.owner_key, task_id, now, old_status, status, note))
        return self.get(task_id)

    def finish_draft(self, task_id: str, draft: str) -> dict[str, Any]:
        if not isinstance(draft, str) or not draft.strip():
            raise ValueError("Draft is empty")
        now = datetime.now(timezone.utc)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM agent_research_tasks WHERE owner_key=%s AND id=%s FOR UPDATE",
                        (self.owner_key, task_id))
            row = cur.fetchone()
            if row is None:
                raise KeyError(task_id)
            if row[0] != "running":
                raise ValueError("Only a running task can finish a draft")
            cur.execute("""INSERT INTO agent_research_drafts(owner_key,task_id,content,updated_at)
                VALUES(%s,%s,%s,%s) ON CONFLICT(owner_key,task_id) DO UPDATE
                SET content=EXCLUDED.content,updated_at=EXCLUDED.updated_at""",
                (self.owner_key, task_id, draft.strip()[:12000], now))
            cur.execute("""UPDATE agent_research_tasks SET status='review_pending',
                blockers='[]',updated_at=%s WHERE owner_key=%s AND id=%s""",
                (now, self.owner_key, task_id))
            cur.execute("""INSERT INTO agent_research_task_events
                (owner_key,task_id,at,old_status,new_status,note)
                VALUES (%s,%s,%s,'running','review_pending',
                    'Draft saved; independent evidence review pending')""",
                (self.owner_key, task_id, now))
        return self.get(task_id)

    def load_draft(self, task_id: str) -> str | None:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT d.content FROM agent_research_drafts d
                JOIN agent_research_tasks t ON t.owner_key=d.owner_key AND t.id=d.task_id
                WHERE d.owner_key=%s AND d.task_id=%s""", (self.owner_key, task_id))
            row = cur.fetchone()
        return row[0] if row else None

    def touch_running(self, task_id: str) -> bool:
        """Refresh a running task heartbeat without crossing owner boundaries."""
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""UPDATE agent_research_tasks SET updated_at=now()
                WHERE owner_key=%s AND id=%s AND status='running'""",
                (self.owner_key, task_id))
            return cur.rowcount == 1

    def history(self, task_id: str) -> list[dict[str, Any]]:
        self.get(task_id)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT event_id,task_id,at,old_status,new_status,note
                FROM agent_research_task_events WHERE owner_key=%s AND task_id=%s
                ORDER BY event_id""", (self.owner_key, task_id))
            rows = cur.fetchall()
        return [dict(zip(("event_id","task_id","at","old_status","new_status","note"), row))
                for row in rows]

    def recover_stale_running(self, *, stale_after_seconds: int = 3600,
                              now: datetime | None = None) -> list[str]:
        if stale_after_seconds < 1:
            raise ValueError("stale_after_seconds must be positive")
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("now must have a timezone")
        threshold = now.astimezone(timezone.utc) - timedelta(seconds=stale_after_seconds)
        recovered = []
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT id,status FROM agent_research_tasks
                WHERE owner_key=%s AND status='running' AND updated_at <= %s
                ORDER BY id FOR UPDATE""", (self.owner_key, threshold))
            rows = cur.fetchall()
            for task_id, old_status in rows:
                cur.execute("""UPDATE agent_research_tasks SET status='blocked',
                    blockers=%s,updated_at=%s WHERE owner_key=%s AND id=%s AND status='running'""",
                    (json.dumps(["Interrupted task; review before retry"]), now,
                     self.owner_key, task_id))
                if cur.rowcount:
                    cur.execute("""INSERT INTO agent_research_task_events
                        (owner_key,task_id,at,old_status,new_status,note)
                        VALUES (%s,%s,%s,%s,'blocked',
                            'Stale running task recovered; manual retry required')""",
                        (self.owner_key, task_id, now, old_status))
                    recovered.append(task_id)
        return recovered

    def import_tasks(self, validated: list[tuple[str, str, str | None, str]]) -> int:
        """Import validated exports as new planned tasks, never restoring status."""
        now = datetime.now(timezone.utc)
        with self._connection() as conn, conn.cursor() as cur:
            for title, goal, draft, provenance in validated:
                task_id = str(uuid.uuid4())
                cur.execute("""INSERT INTO agent_research_tasks
                    (owner_key,id,title,goal,status,created_at,updated_at)
                    VALUES(%s,%s,%s,%s,'planned',%s,%s)""",
                    (self.owner_key, task_id, title, goal, now, now))
                cur.execute("""INSERT INTO agent_research_task_events
                    (owner_key,task_id,at,old_status,new_status,note)
                    VALUES(%s,%s,%s,NULL,'planned',%s)""",
                    (self.owner_key, task_id, now,
                     "Imported backup; re-verification required. Untrusted original record: " + provenance))
                if draft:
                    cur.execute("""INSERT INTO agent_research_drafts
                        (owner_key,task_id,content,updated_at) VALUES(%s,%s,%s,%s)""",
                        (self.owner_key, task_id, draft, now))
        return len(validated)
