"""Owner-scoped, authenticated PostgreSQL leader lease (not wired into runtime).

Only provisioned nodes may participate. Epochs must monotonically fence old
leaders. This is a proposed interface; implementation follows RED CI.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


class LostLeadership(RuntimeError):
    pass


@dataclass(frozen=True)
class LeaderToken:
    owner_key: str
    scope: str
    node_id: str
    epoch: int


def credential_digest(owner_key: str, node_id: str, secret: str) -> bytes:
    """Digest an independently provisioned high-entropy node credential."""
    if not isinstance(secret, str) or len(secret) < 32:
        raise ValueError("32+ character capability required")
    payload = ("cano-queen-node-v1\x00" + owner_key + "\x00" +
               node_id + "\x00" + secret).encode("utf-8")
    return hashlib.sha256(payload).digest()


class PostgresLeaderLease:
    def __init__(self, database_url: str, *, owner_key: str, node_id: str,
                 node_secret: str, connect=None):
        if not database_url:
            raise ValueError("database_url required")
        if not isinstance(owner_key, str) or not owner_key.strip() or len(owner_key) > 128:
            raise ValueError("valid owner_key required")
        if not isinstance(node_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", node_id):
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

    def acquire(self, scope: str, *, ttl_seconds: int = 10) -> LeaderToken | None:
        raise NotImplementedError("transactional lease not implemented")

    def renew(self, token: LeaderToken, *, ttl_seconds: int = 10) -> LeaderToken | None:
        raise NotImplementedError("fenced renewal not implemented")

    def release(self, token: LeaderToken) -> bool:
        raise NotImplementedError("fenced release not implemented")

    def assert_fence(self, cursor, token: LeaderToken) -> None:
        """Lock the row in the caller's existing write transaction."""
        raise NotImplementedError("transactional fencing not implemented")
