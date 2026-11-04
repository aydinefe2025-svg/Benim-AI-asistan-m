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
                cur.execute("""CREATE TABLE IF NOT EXISTS private_colony_snapshot_revisions (
                    revision BIGSERIAL PRIMARY KEY,
                    owner_key TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    archived_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
                cur.execute("""CREATE INDEX IF NOT EXISTS
                    idx_colony_revision_owner ON private_colony_snapshot_revisions
                    (owner_key, revision DESC)""")

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

    def save_verified(self, owner_key, payload):
        """Save and read back an exact owner-scoped colony snapshot.

        A successful SQL commit alone is insufficient evidence that the
        correct owner's complete payload can be recovered. The caller must
        report backup success only when the readback matches exactly.
        """
        self.save(owner_key, payload)
        actual = self.load(owner_key)
        if actual != payload:
            raise RuntimeError("Colony snapshot readback mismatch")
        return True

    def save_versioned_verified(self, owner_key, payload):
        """Atomically archive prior distinct snapshot before overwriting it.

        Cap history at 20 versions per owner; fail closed rather than silently
        deleting old backups. Verify latest snapshot by fresh-connection readback.
        Caller must supply an authenticated and stable owner key.
        """
        if not isinstance(owner_key, str) or not owner_key.strip():
            raise ValueError("Authenticated owner required")
        if not isinstance(payload, dict) or not all(
            isinstance(payload.get(k), list) for k in ("agents", "feedback", "reviews")
        ):
            raise ValueError("Invalid colony snapshot")
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        if len(serialized.encode("utf-8")) > 2_000_000:
            raise ValueError("Snapshot exceeds quota")

        with self.connect(self.database_url, connect_timeout=8) as db:
            with db.cursor() as cur:
                # Serialize concurrent writes from multiple tabs for one owner.
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s)::bigint)",
                            ("cano-colony-backup:" + owner_key,))
                cur.execute("SELECT payload FROM private_colony_snapshots "
                            "WHERE owner_key=%s FOR UPDATE", (owner_key,))
                prior_row = cur.fetchone()
                prior = prior_row[0] if prior_row else None
                if isinstance(prior, str):
                    prior = json.loads(prior)
                if prior != payload:
                    if prior is not None:
                        cur.execute("SELECT COUNT(*) FROM private_colony_snapshot_revisions "
                                    "WHERE owner_key=%s", (owner_key,))
                        if cur.fetchone()[0] >= 20:
                            raise RuntimeError("Colony backup revision quota reached; export required")
                        cur.execute("INSERT INTO private_colony_snapshot_revisions "
                                    "(owner_key,payload) VALUES (%s,%s::jsonb)",
                                    (owner_key, json.dumps(prior, ensure_ascii=False)))
                    cur.execute("""INSERT INTO private_colony_snapshots (owner_key,payload)
                        VALUES (%s,%s::jsonb) ON CONFLICT(owner_key)
                        DO UPDATE SET payload=EXCLUDED.payload, updated_at=now()""",
                                (owner_key, serialized))
        if self.load(owner_key) != payload:
            raise RuntimeError("Colony snapshot readback mismatch")
        return True

    def list_archived(self, owner_key):
        if not isinstance(owner_key, str) or not owner_key.strip():
            raise ValueError("Authenticated owner required")
        with self.connect(self.database_url, connect_timeout=8) as db:
            with db.cursor() as cur:
                cur.execute("SELECT revision, archived_at FROM private_colony_snapshot_revisions "
                            "WHERE owner_key=%s ORDER BY revision DESC", (owner_key,))
                return [{"revision": row[0], "archived_at": row[1].isoformat()}
                        for row in cur.fetchall()]

    def load_archived(self, owner_key, revision):
        if not isinstance(owner_key, str) or not owner_key.strip():
            raise ValueError("Authenticated owner required")
        if type(revision) is not int or revision < 1:
            raise ValueError("Invalid snapshot revision")
        with self.connect(self.database_url, connect_timeout=8) as db:
            with db.cursor() as cur:
                cur.execute("SELECT payload FROM private_colony_snapshot_revisions "
                            "WHERE owner_key=%s AND revision=%s",
                            (owner_key, revision))
                row = cur.fetchone()
        return (json.loads(row[0]) if isinstance(row[0], str) else row[0]) if row else None

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
