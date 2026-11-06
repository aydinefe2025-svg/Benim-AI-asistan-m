"""Owner-scoped durable records for bounded Organism Lab simulations.

Uses the already provisioned organism_lab_records table; this module never
creates or alters schema. Each immutable record is keyed by its content hash,
and every write is verified through a fresh-connection readback.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import re


class OrganismLabPersistenceError(RuntimeError):
    """A safe, user-presentable persistence failure."""


class OrganismLabPermissionsError(RuntimeError):
    """Non-sensitive runtime grant details for safe operations diagnostics."""

    def __init__(self, role_name, can_select, can_insert):
        super().__init__("Organism Lab runtime table grants are incomplete")
        self.role_name = role_name
        self.can_select = bool(can_select)
        self.can_insert = bool(can_insert)


class OrganismLabStore:
    COLLECTION = "simulation"
    RECORD_PREFIX = "cano-organism-lab-v1-"
    MAX_RECORD_BYTES = 1_000_000

    def __init__(self, owner_key: str, database_url: str, *, connect=None):
        if not isinstance(owner_key, str) or not re.fullmatch(r"oidc_[0-9a-f]{64}", owner_key):
            raise ValueError("Verified owner identity required")
        if not isinstance(database_url, str) or not database_url.strip():
            raise ValueError("Database URL required")
        if connect is None:
            import psycopg
            connect = psycopg.connect
        self.owner_key = owner_key
        self.database_url = database_url
        self._connect = connect

    @contextmanager
    def _connection(self):
        with self._connect(self.database_url, connect_timeout=8) as db:
            # The Neon RLS policies bind all reads/writes in this transaction
            # to the authenticated HMAC owner key.
            with db.cursor() as cur:
                cur.execute("SELECT set_config('cano.owner_key', %s, true)",
                            (self.owner_key,))
            yield db

    def verify_schema(self):
        """Check only the pre-provisioned table and least required grants."""
        with self._connection() as db, db.cursor() as cur:
            # Check permissions first so a restricted app role can report a
            # boolean denial instead of leaking a driver error message.
            cur.execute("""SELECT current_user,
                has_table_privilege(current_user, 'public.organism_lab_records', 'SELECT'),
                has_table_privilege(current_user, 'public.organism_lab_records', 'INSERT')""")
            result = cur.fetchone()
            if not result:
                raise OrganismLabPersistenceError("Organism Lab privilege check returned no result")
            role_name, can_select, can_insert = result
            if not can_select or not can_insert:
                raise OrganismLabPermissionsError(role_name, can_select, can_insert)
            cur.execute("""SELECT owner_key, collection, record_id, payload, updated_at
                FROM public.organism_lab_records LIMIT 0""")
            return role_name

    @classmethod
    def _record_id(cls, kind: str, raw: bytes) -> tuple[str, str]:
        if kind not in {"campaign", "world"}:
            raise ValueError("Unknown Organism Lab record type")
        digest = hashlib.sha256(raw).hexdigest()
        return f"{cls.RECORD_PREFIX}{kind}-{digest}", digest

    @staticmethod
    def _decode_payload(payload) -> tuple[bytes, str]:
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict) or payload.get("format") != 1:
            raise ValueError("Unsupported Organism Lab record format")
        encoded = payload.get("data_b64")
        expected = payload.get("sha256")
        if not isinstance(encoded, str) or not isinstance(expected, str):
            raise ValueError("Invalid Organism Lab record")
        raw = base64.b64decode(encoded, validate=True)
        actual = hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(actual, expected):
            raise ValueError("Organism Lab record integrity check failed")
        return raw, actual

    def save_verified(self, kind: str, data: bytes) -> dict:
        if not isinstance(data, bytes) or not data or len(data) > self.MAX_RECORD_BYTES:
            raise ValueError("Organism Lab record size is invalid")
        record_id, digest = self._record_id(kind, data)
        payload = json.dumps({
            "format": 1,
            "sha256": digest,
            "data_b64": base64.b64encode(data).decode("ascii"),
        }, separators=(",", ":"))
        with self._connection() as db, db.cursor() as cur:
            cur.execute("""INSERT INTO public.organism_lab_records
                (owner_key, collection, record_id, payload)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (owner_key, collection, record_id) DO NOTHING""",
                (self.owner_key, self.COLLECTION, record_id, payload))
        # Read through a new connection so success means durable, owner-scoped
        # data can actually be recovered after the write transaction commits.
        row = self._load_row(record_id)
        if row is None:
            raise OrganismLabPersistenceError("Organism Lab record readback failed")
        actual, actual_digest = self._decode_payload(row[0])
        if actual != data or not hmac.compare_digest(actual_digest, digest):
            raise OrganismLabPersistenceError("Organism Lab record readback mismatch")
        return {"record_id": record_id, "sha256": digest, "data": actual}

    def _load_row(self, record_id: str):
        with self._connection() as db, db.cursor() as cur:
            cur.execute("""SELECT payload, updated_at
                FROM public.organism_lab_records
                WHERE owner_key=%s AND collection=%s AND record_id=%s""",
                (self.owner_key, self.COLLECTION, record_id))
            return cur.fetchone()

    def list_recent(self, limit: int = 10) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError("Invalid Organism Lab history limit")
        with self._connection() as db, db.cursor() as cur:
            cur.execute("""SELECT record_id, payload, updated_at
                FROM public.organism_lab_records
                WHERE owner_key=%s AND collection=%s AND record_id LIKE %s
                ORDER BY updated_at DESC, record_id DESC LIMIT %s""",
                (self.owner_key, self.COLLECTION, self.RECORD_PREFIX + "%", limit))
            rows = cur.fetchall()
        records = []
        for record_id, payload, updated_at in rows:
            raw, digest = self._decode_payload(payload)
            kind = record_id[len(self.RECORD_PREFIX):].split("-", 1)[0]
            if kind not in {"campaign", "world"}:
                continue
            if not hmac.compare_digest(record_id.rsplit("-", 1)[-1], digest):
                raise ValueError("Organism Lab record identifier mismatch")
            document = json.loads(raw.decode("utf-8"))
            records.append({"record_id": record_id, "kind": kind,
                            "sha256": digest, "data": raw,
                            "document": document, "updated_at": updated_at})
        return records
