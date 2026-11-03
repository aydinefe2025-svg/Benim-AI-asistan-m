"""Owner-scoped PostgreSQL snapshot of bounded agent colony records.

Only use after authenticated owner identification; no automatic schema creation.
"""
from __future__ import annotations

import json
import os


class ColonySnapshotStore:
    def __init__(self, database_url=None, *, connect=None):
        self.database_url = database_url or os.environ.get("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL required")
        if connect is None:
            import psycopg
            connect = psycopg.connect
        self.connect = connect

    def initialize(self):
        with self.connect(self.database_url, connect_timeout=8) as db:
            with db.cursor() as cur:
                cur.execute("""CREATE TABLE IF NOT EXISTS private_colony_snapshots (
                    owner_key TEXT PRIMARY KEY,
                    payload JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")

    def save(self, owner_key, payload):
        if not isinstance(owner_key, str) or not owner_key.strip():
            raise ValueError("Authenticated owner required")
        if not isinstance(payload, dict) or not all(
            isinstance(payload.get(k), list) for k in ("agents", "feedback", "reviews")
        ):
            raise ValueError("Invalid colony snapshot")
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(data.encode("utf-8")) > 2_000_000:
            raise ValueError("Snapshot exceeds quota")
        with self.connect(self.database_url, connect_timeout=8) as db:
            with db.cursor() as cur:
                cur.execute("""INSERT INTO private_colony_snapshots (owner_key,payload)
                    VALUES (%s,%s::jsonb) ON CONFLICT(owner_key)
                    DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()""",
                    (owner_key, data))

    def load(self, owner_key):
        if not isinstance(owner_key, str) or not owner_key.strip():
            raise ValueError("Authenticated owner required")
        with self.connect(self.database_url, connect_timeout=8) as db:
            with db.cursor() as cur:
                cur.execute("SELECT payload FROM private_colony_snapshots WHERE owner_key=%s",
                            (owner_key,))
                row = cur.fetchone()
        if row is None:
            return None
        return json.loads(row[0]) if isinstance(row[0], str) else row[0]
