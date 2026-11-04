"""Owner-scoped, registered-node PostgreSQL leader lease with epoch fencing.

Admin provisions public.cano_queen_authorized_nodes and public.cano_queen_leases.
This runtime never creates a table, enrolls nodes, or calls a remote provider on
import. Protected database writes must invoke assert_fence on the SAME write
transaction. External side effects are not fenced by this helper.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re


class LostLeadership(RuntimeError):
    """An expired, revoked, or superseded leader cannot commit a fenced write."""


@dataclass(frozen=True)
class LeaderToken:
    owner_key: str
    scope: str
    node_id: str
    epoch: int


def credential_digest(owner_key: str, node_id: str, secret: str) -> bytes:
    """Owner/node-bound digest of a separately provisioned random secret."""
    if not isinstance(secret, str) or len(secret) < 32:
        raise ValueError("32+ character capability required")
    payload = ("cano-queen-node-v1\x00" + owner_key + "\x00" +
               node_id + "\x00" + secret).encode("utf-8")
    return hashlib.sha256(payload).digest()


class PostgresLeaderLease:
    """DB-clock lease with monotonically increasing owner/scope epochs.

    A separately provisioned high-entropy node capability is required; do
    not treat a node label as authentication. TTL bounded to 1..60 seconds.
    """

    def __init__(self, database_url: str, *, owner_key: str, node_id: str,
                 node_secret: str, connect=None):
        if not database_url:
            raise ValueError("database_url required")
        if (not isinstance(owner_key, str) or not owner_key.strip()
                or len(owner_key) > 128):
            raise ValueError("valid owner_key required")
        if (not isinstance(node_id, str)
                or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", node_id)):
            raise ValueError("valid node_id required")
        credential_digest(owner_key, node_id, node_secret)
        self.database_url = database_url
        self.owner_key = owner_key
        self.node_id = node_id
        self._secret = node_secret
        if connect is None:
            import psycopg
            connect = psycopg.connect
        self._connect = connect

    @staticmethod
    def _scope(scope: str) -> str:
        if not isinstance(scope, str) or not re.fullmatch(r"[a-z][a-z0-9._-]{0,63}", scope):
            raise ValueError("invalid lease scope")
        return scope

    @staticmethod
    def _ttl(value: int) -> int:
        if type(value) is not int or not 1 <= value <= 60:
            raise ValueError("leader TTL must be 1..60 seconds")
        return value

    def _check_token(self, token: LeaderToken) -> None:
        if (not isinstance(token, LeaderToken)
                or token.owner_key != self.owner_key
                or token.node_id != self.node_id
                or type(token.epoch) is not int or token.epoch < 1):
            raise PermissionError("leader token identity mismatch")
        self._scope(token.scope)

    def _authorize(self, cur) -> None:
        cur.execute("""SELECT verifier FROM public.cano_queen_authorized_nodes
            WHERE owner_key=%s AND node_id=%s AND enabled=TRUE""",
            (self.owner_key, self.node_id))
        row = cur.fetchone()
        expected = credential_digest(self.owner_key, self.node_id, self._secret)
        if not row or not hmac.compare_digest(bytes(row[0]), expected):
            raise PermissionError("unrecognized or revoked leader node")

    def acquire(self, scope: str, *, ttl_seconds: int = 10) -> LeaderToken | None:
        scope = self._scope(scope)
        ttl_seconds = self._ttl(ttl_seconds)
        with self._connect(self.database_url, connect_timeout=8) as db, db.cursor() as cur:
            self._authorize(cur)
            # Atomic conditional UPSERT uses row locks and PostgreSQL time.
            cur.execute("""INSERT INTO public.cano_queen_leases
                (owner_key,scope,node_id,epoch,expires_at)
                VALUES (%s,%s,%s,1,clock_timestamp()+make_interval(secs => %s))
                ON CONFLICT (owner_key,scope) DO UPDATE SET
                    node_id=EXCLUDED.node_id,
                    epoch=cano_queen_leases.epoch+1,
                    expires_at=clock_timestamp()+make_interval(secs => %s),
                    claimed_at=clock_timestamp()
                WHERE cano_queen_leases.expires_at<=clock_timestamp()
                RETURNING epoch""",
                (self.owner_key,scope,self.node_id,ttl_seconds,ttl_seconds))
            row = cur.fetchone()
        return (LeaderToken(self.owner_key,scope,self.node_id,row[0])
                if row is not None else None)

    def renew(self, token: LeaderToken, *, ttl_seconds: int = 10) -> LeaderToken | None:
        self._check_token(token)
        ttl_seconds = self._ttl(ttl_seconds)
        with self._connect(self.database_url, connect_timeout=8) as db, db.cursor() as cur:
            self._authorize(cur)
            cur.execute("""UPDATE public.cano_queen_leases
                SET expires_at=clock_timestamp()+make_interval(secs => %s)
                WHERE owner_key=%s AND scope=%s AND node_id=%s AND epoch=%s
                  AND expires_at>clock_timestamp() RETURNING epoch""",
                (ttl_seconds,token.owner_key,token.scope,token.node_id,token.epoch))
            row=cur.fetchone()
        return token if row else None

    def release(self, token: LeaderToken) -> bool:
        self._check_token(token)
        with self._connect(self.database_url, connect_timeout=8) as db, db.cursor() as cur:
            self._authorize(cur)
            cur.execute("""UPDATE public.cano_queen_leases
                SET expires_at=clock_timestamp()
                WHERE owner_key=%s AND scope=%s AND node_id=%s AND epoch=%s
                  AND expires_at>clock_timestamp() RETURNING epoch""",
                (token.owner_key,token.scope,token.node_id,token.epoch))
            accepted = cur.fetchone() is not None
        return accepted

    def assert_fence(self, cursor, token: LeaderToken) -> None:
        """Authorize+lock lease in caller's ongoing database write transaction.

        The caller MUST perform the protected database mutation before it
        commits this transaction. External API effects need separate fencing.
        """
        self._check_token(token)
        self._authorize(cursor)
        cursor.execute("""SELECT node_id,epoch,expires_at
            FROM public.cano_queen_leases
            WHERE owner_key=%s AND scope=%s FOR UPDATE""",
            (token.owner_key,token.scope))
        row=cursor.fetchone()
        if row is None or row[0]!=token.node_id or row[1]!=token.epoch:
            raise LostLeadership("leader epoch superseded")
        cursor.execute("SELECT %s::timestamptz > clock_timestamp()", (row[2],))
        if not cursor.fetchone()[0]:
            raise LostLeadership("leader lease expired")
