"""Real Postgres 17 queen lease tests on a disposable, synthetic CI database.

Do NOT import, migrate or run against Render. Includes process kill/restart,
concurrent claims, owner isolation, revoked credentials and fenced DB writes.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit

import psycopg

from core.postgres_leader_lease import (
    LeaderToken, LostLeadership, PostgresLeaderLease, credential_digest,
)

DSN = os.environ.get("TEST_DATABASE_URL", "")
OWNER_A = "oidc_ci_owner_a"
OWNER_B = "oidc_ci_owner_b"


def secret(node: str) -> str:
    return "synthetic-local-leader-ci-capability-" + node + "-never-live"


def client(owner: str, node: str) -> PostgresLeaderLease:
    return PostgresLeaderLease(
        DSN, owner_key=owner, node_id=node, node_secret=secret(node))


def guard_ci():
    url = urlsplit(DSN)
    if (os.environ.get("CANO_QUEEN_TEST") != "1"
            or url.scheme not in {"postgres", "postgresql"}
            or url.hostname not in {"localhost", "127.0.0.1"}
            or url.path != "/ci_queen_test"):
        raise RuntimeError("CANO queen test refuses non-disposable database")


def provision():
    sql_path = Path(__file__).with_name("provision_cano_queen_leases.sql")
    ddl = sql_path.read_text(encoding="utf-8")
    with psycopg.connect(DSN, connect_timeout=8) as conn, conn.cursor() as cur:
        cur.execute(ddl)
        cur.execute("""CREATE TABLE IF NOT EXISTS cano_ci_fenced_events (
            owner_key TEXT NOT NULL, scope TEXT NOT NULL, event TEXT NOT NULL,
            PRIMARY KEY (owner_key,scope,event))""")
        for owner in (OWNER_A, OWNER_B):
            for node in (["queen-a", "queen-b", "queen-c"] +
                         [f"race-{i}" for i in range(8)]):
                cur.execute("""INSERT INTO cano_queen_authorized_nodes
                    (owner_key,node_id,verifier,enabled)
                    VALUES (%s,%s,%s,TRUE)
                    ON CONFLICT(owner_key,node_id)
                    DO UPDATE SET verifier=EXCLUDED.verifier, enabled=TRUE""",
                    (owner, node, credential_digest(owner,node,secret(node))))


def fenced_write(store: PostgresLeaderLease, token: LeaderToken, label: str):
    # Check AND write are within one transaction with a row lock; merely
    # checking a token outside this transaction would not fence stale writes.
    with psycopg.connect(DSN, connect_timeout=8) as conn, conn.cursor() as cur:
        store.assert_fence(cur, token)
        cur.execute("""INSERT INTO cano_ci_fenced_events
            (owner_key,scope,event) VALUES (%s,%s,%s)""",
            (token.owner_key, token.scope, label))


def read_events(owner: str, scope: str) -> list[str]:
    with psycopg.connect(DSN, connect_timeout=8) as conn, conn.cursor() as cur:
        cur.execute("""SELECT event FROM cano_ci_fenced_events
            WHERE owner_key=%s AND scope=%s ORDER BY event""",
            (owner,scope))
        return [row[0] for row in cur.fetchall()]


def test_leader_fence():
    a, b = client(OWNER_A,"queen-a"), client(OWNER_A,"queen-b")
    token_a = a.acquire("main", ttl_seconds=8)
    assert token_a is not None and token_a.epoch == 1
    assert b.acquire("main", ttl_seconds=8) is None, "split brain"
    fenced_write(a,token_a,"before")
    with psycopg.connect(DSN, connect_timeout=8) as conn, conn.cursor() as cur:
        # Admin-only failure injection on a disposable test DB.
        cur.execute("""UPDATE cano_queen_leases
            SET expires_at=clock_timestamp() - interval '1 second'
            WHERE owner_key=%s AND scope='main'""", (OWNER_A,))
    token_b = b.acquire("main", ttl_seconds=8)
    assert token_b is not None and token_b.epoch == 2
    assert a.renew(token_a, ttl_seconds=8) is None
    assert a.release(token_a) is False
    try:
        fenced_write(a,token_a,"stale-should-not-appear")
    except LostLeadership:
        pass
    else:
        raise AssertionError("stale epoch committed a fenced database write")
    fenced_write(b,token_b,"after")
    assert read_events(OWNER_A,"main") == ["after","before"]
    assert b.renew(token_b, ttl_seconds=8) == token_b
    assert b.release(token_b) is True
    assert b.release(token_b) is False
    token_c = a.acquire("main", ttl_seconds=8)
    assert token_c is not None and token_c.epoch == 3


def test_auth_and_isolation():
    a = client(OWNER_A,"queen-a")
    other = client(OWNER_B,"queen-a")
    left = a.acquire("isolated", ttl_seconds=6)
    right = other.acquire("isolated", ttl_seconds=6)
    assert left and right and left.epoch == right.epoch == 1
    bad = PostgresLeaderLease(
        DSN, owner_key=OWNER_A, node_id="queen-b",
        node_secret="intentionally-wrong-token-123456789000000000")
    try:
        bad.acquire("isolated", ttl_seconds=6)
    except PermissionError:
        pass
    else:
        raise AssertionError("unregistered capability claimed lease")
    claimed = a.acquire("revoke", ttl_seconds=6)
    assert claimed is not None
    with psycopg.connect(DSN, connect_timeout=8) as conn, conn.cursor() as cur:
        cur.execute("""UPDATE cano_queen_authorized_nodes SET enabled=FALSE
            WHERE owner_key=%s AND node_id=%s""", (OWNER_A,"queen-a"))
    try:
        a.renew(claimed, ttl_seconds=6)
    except PermissionError:
        pass
    else:
        raise AssertionError("revoked leader renewed")
    try:
        fenced_write(a,claimed,"revoked-should-not-appear")
    except PermissionError:
        pass
    else:
        raise AssertionError("revoked leader wrote into database")
    with psycopg.connect(DSN, connect_timeout=8) as conn, conn.cursor() as cur:
        cur.execute("""UPDATE cano_queen_authorized_nodes SET enabled=TRUE
            WHERE owner_key=%s AND node_id=%s""", (OWNER_A,"queen-a"))


def test_concurrent_claims():
    def ask(i: int):
        return client(OWNER_A, f"race-{i}").acquire(
            "race", ttl_seconds=10)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(ask,range(8)))
    winners = [token for token in results if token is not None]
    assert len(winners) == 1, "Concurrent leaders / no leader"
    assert winners[0].epoch == 1


def test_killed_worker_recovery():
    env = os.environ.copy()
    p = subprocess.Popen(
        [sys.executable, "-m", "scripts.check_cano_pg_queen_lease",
         "--child-claim"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        text=True)
    try:
        line = p.stdout.readline().strip()
        assert line == "CLAIM_EPOCH:1", "child claim did not complete"
    finally:
        p.kill()
        p.wait(timeout=5)
        p.stdout.close()
        p.stderr.close()
    time.sleep(1.45)
    b = client(OWNER_A,"queen-b")
    new = b.acquire("failover", ttl_seconds=7)
    assert new is not None and new.epoch == 2, "crash recovery failed"
    old_token = LeaderToken(OWNER_A,"failover","queen-a",1)
    try:
        fenced_write(client(OWNER_A,"queen-a"),old_token,"stale")
    except LostLeadership:
        pass
    else:
        raise AssertionError("killed old leader could still mutate")
    fenced_write(b,new,"new-leader")
    assert read_events(OWNER_A,"failover") == ["new-leader"]


def main():
    guard_ci()
    if "--child-claim" in sys.argv:
        t = client(OWNER_A,"queen-a").acquire("failover", ttl_seconds=1)
        if t is None:
            raise AssertionError("child failed claim")
        print("CLAIM_EPOCH:" + str(t.epoch), flush=True)
        while True:
            time.sleep(10)

    provision()
    test_leader_fence()
    test_auth_and_isolation()
    test_concurrent_claims()
    test_killed_worker_recovery()
    print("CANO_QUEEN_PG17: 4/4 scenarios PASS; "
          "concurrent 1/8 leader, epoch 1->2->3, "
          "stale/revoked writes refused, owner isolation, "
          "SIGKILL worker recovered via new process")


if __name__ == "__main__":
    main()
