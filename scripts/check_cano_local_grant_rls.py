"""Disposable PG17/18 CI: local HTTP capability path under queue owner RLS."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from core.postgres_authorized_queue import PostgresAuthorizedQueue
from core.postgres_local_grant import PostgresLocalGrant
from core.local_task_handoff import run_ticket

ADMIN = "postgresql://ci_user:synthetic-ci-only@localhost:5432/ci_persistence"
RUNTIME = "postgresql://cano_ci_restricted:synthetic-role-only@localhost:5432/ci_persistence"


def denied(fn):
    try:
        fn()
    except PermissionError:
        return
    raise AssertionError("Unauthorized grant operation accepted")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("TEST_DATABASE_URL") != ADMIN:
        raise SystemExit("Disposable CI database required")
    a = PostgresAuthorizedQueue(RUNTIME, owner_key="ci-local-rls-a")
    b = PostgresAuthorizedQueue(RUNTIME, owner_key="ci-local-rls-b")
    job = a.enqueue("local", "Synthetic local grant", approved=True)
    issued = PostgresLocalGrant.issue(a, approved=True)
    assert issued["id"] == job["id"]
    token = issued["grant"]
    forged = token[:-1] + ("0" if token[-1] != "0" else "1")
    denied(lambda: PostgresLocalGrant(RUNTIME).take(forged))
    denied(lambda: PostgresLocalGrant.revoke(b, job["id"], approved=True))
    print("LOCAL_GRANT_RLS_FIXTURE_PASS", flush=True)
    try:
        ticket = PostgresLocalGrant(RUNTIME).take(token)
    except PermissionError:
        print("LOCAL_GRANT_RLS_RED: valid capability cannot resolve owner under default-deny RLS", flush=True)
        raise
    assert ticket["job_id"] == job["id"]
    assert "owner_key" not in ticket and "lease_token" not in ticket
    denied(lambda: PostgresLocalGrant(RUNTIME).take(token))
    with TemporaryDirectory() as folder:
        result = run_ticket(ticket, Path(folder)/"worker.db", lambda _: "Synthetic draft", approved=True)
        receipt = PostgresLocalGrant(RUNTIME).finish(token, result)
        assert receipt["readback"] and not receipt["verified"]
        denied(lambda: PostgresLocalGrant(RUNTIME).finish(token, result))
    assert a.get(job["id"])["state"] == "review_pending"
    assert a.get(job["id"])["attempts"] == 1
    assert b.list() == []
    revocable = a.enqueue("revoke", "Synthetic revoke", approved=True)
    revoke_grant = PostgresLocalGrant.issue(a, approved=True)
    assert PostgresLocalGrant.revoke(a, revocable["id"], approved=True)["status"] == "blocked"
    denied(lambda: PostgresLocalGrant(RUNTIME).take(revoke_grant["grant"]))
    print("LOCAL_GRANT_RLS_PASS: valid capability, forged/replay rejection, result readback and revoke")


if __name__ == "__main__":
    main()
