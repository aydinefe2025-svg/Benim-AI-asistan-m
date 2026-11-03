"""Private, durable PostgreSQL storage for user-controlled memory entries.

No network connection is made on import. Database URL is read only at runtime
and never logged. This module does not automatically migrate session memories.
"""
from __future__ import annotations

import json
import os


class DatabaseNotConfigured(RuntimeError):
    pass


class PostgresMemoryStore:
    def __init__(self, database_url: str | None = None, *, connect=None):
        self.database_url = database_url or os.environ.get("DATABASE_URL")
        if not self.database_url:
            raise DatabaseNotConfigured("DATABASE_URL is required")
        if connect is None:
            import psycopg
            connect = psycopg.connect
        self._connect = connect

    def _connection(self):
        return self._connect(self.database_url, connect_timeout=8)

    def initialize(self):
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS private_memory_entries (
                        owner_key TEXT NOT NULL,
                        entry_id TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (owner_key, entry_id)
                    )
                """)

    def save(self, owner_key: str, entry: dict):
        if not isinstance(owner_key, str) or not owner_key.strip():
            raise ValueError("owner_key required")
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
            raise ValueError("entry with nonempty id required")
        payload = json.dumps(entry, ensure_ascii=False, allow_nan=False)
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO private_memory_entries (owner_key, entry_id, payload)
                    VALUES (%s, %s, %s::jsonb)
                    ON CONFLICT (owner_key, entry_id)
                    DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()
                """, (owner_key, entry["id"], payload))

    def list(self, owner_key: str) -> list[dict]:
        if not isinstance(owner_key, str) or not owner_key.strip():
            raise ValueError("owner_key required")
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT payload FROM private_memory_entries
                    WHERE owner_key=%s ORDER BY updated_at, entry_id
                """, (owner_key,))
                return [json.loads(row[0]) if isinstance(row[0], str) else row[0]
                        for row in cur.fetchall()]

    def delete(self, owner_key: str, entry_id: str):
        if not owner_key or not entry_id:
            raise ValueError("owner_key and entry_id required")
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM private_memory_entries
                    WHERE owner_key=%s AND entry_id=%s
                """, (owner_key, entry_id))
