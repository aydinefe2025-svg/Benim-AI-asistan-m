"""Account-scoped CANO chat transcript persistence on the existing Neon Postgres.

Unlike saved knowledge notes, this store is for the visible chat only.
Fail closed if the owner scope or dedicated table is unavailable.
"""
from __future__ import annotations

import json
import re

MAX_MESSAGES = 150
MAX_BYTES = 128_000


class ChatHistoryStore:
    def __init__(self, database_url, owner_key, *, connect=None):
        if not isinstance(database_url, str) or not database_url.startswith(
                ("postgres://", "postgresql://")):
            raise ValueError("A configured Neon PostgreSQL connection is required")
        if not isinstance(owner_key, str) or not re.fullmatch(
                r"oidc_[0-9a-f]{64}", owner_key):
            raise PermissionError("Verified owner required")
        self.database_url, self.owner_key = database_url, owner_key
        self._connect = connect

    def _db(self):
        if self._connect is not None:
            return self._connect(self.database_url)
        import psycopg
        return psycopg.connect(self.database_url, connect_timeout=8)

    def _scope(self, cursor):
        cursor.execute("SELECT set_config('cano.owner_key', %s, true)",
                       (self.owner_key,))

    def verify_schema(self):
        with self._db() as conn, conn.cursor() as cursor:
            self._scope(cursor)
            cursor.execute(
                "SELECT owner_key, payload, updated_at "
                "FROM public.cano_chat_histories LIMIT 0"
            )

    @staticmethod
    def _validate(messages):
        if not isinstance(messages, list):
            raise ValueError("Chat transcript must be a list")
        checked = []
        for message in messages[-MAX_MESSAGES:]:
            if not isinstance(message, dict) or message.get("role") not in (
                    "user", "assistant"):
                raise ValueError("Invalid chat role")
            content = message.get("content")
            if not isinstance(content, str) or len(content) > 8000:
                raise ValueError("Invalid chat content")
            checked.append({"role": message["role"], "content": content})
        raw = json.dumps(checked, ensure_ascii=False, allow_nan=False)
        if len(raw.encode("utf-8")) > MAX_BYTES:
            raise ValueError("Chat transcript exceeds size limit")
        return checked, raw

    def load(self):
        with self._db() as conn, conn.cursor() as cursor:
            self._scope(cursor)
            cursor.execute(
                "SELECT payload FROM public.cano_chat_histories "
                "WHERE owner_key = %s", (self.owner_key,)
            )
            row = cursor.fetchone()
        if row is None:
            return []
        payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        checked, _ = self._validate(payload)
        return checked

    def save(self, messages):
        checked, raw = self._validate(messages)
        with self._db() as conn, conn.cursor() as cursor:
            self._scope(cursor)
            cursor.execute(
                "INSERT INTO public.cano_chat_histories"
                " (owner_key, payload, updated_at) VALUES (%s,%s::jsonb,now()) "
                "ON CONFLICT (owner_key) DO UPDATE SET "
                "payload=EXCLUDED.payload,updated_at=now()",
                (self.owner_key, raw)
            )
            cursor.execute(
                "SELECT payload FROM public.cano_chat_histories "
                "WHERE owner_key = %s", (self.owner_key,)
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Chat save was not readable")
            seen = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            if seen != checked:
                raise RuntimeError("Chat save verification mismatch")
        return len(checked)
