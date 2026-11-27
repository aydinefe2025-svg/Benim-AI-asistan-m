"""Disposable PG17/18 CI: owner-context RLS for the authorized queue."""
import os
import psycopg
from core.postgres_authorized_queue import PostgresAuthorizedQueue
from scripts.check_postgres_authorized_queue import provision_synthetic_schema

ADMIN = "postgresql://ci_user:synthetic-ci-only@localhost:5432/ci_persistence"
RUNTIME = "postgresql://cano_ci_restricted:synthetic-role-only@localhost:5432/ci_persistence"
TABLES = ("cano_authorized_jobs", "cano_authorized_job_events")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("TEST_DATABASE_URL") != ADMIN:
        raise SystemExit("Disposable CI database required")
    provision_synthetic_schema(ADMIN)
    a, b = "ci-queue-rls-a", "ci-queue-rls-b"
    seed = PostgresAuthorizedQueue(ADMIN, owner_key=a).enqueue(
        "seed", "Synthetic seed", approved=True)
    with psycopg.connect(ADMIN) as conn:
        for table in TABLES:
            conn.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            conn.execute(f"""CREATE POLICY ci_owner_scope ON public.{table}
                FOR ALL TO cano_ci_restricted
                USING (owner_key = nullif(current_setting('cano.owner_key', true), ''))
                WITH CHECK (owner_key = nullif(current_setting('cano.owner_key', true), ''))""")
            conn.execute(f"GRANT SELECT, INSERT ON public.{table} TO cano_ci_restricted")
        conn.execute("GRANT UPDATE ON public.cano_authorized_jobs TO cano_ci_restricted")
        conn.execute("GRANT USAGE ON SEQUENCE public.cano_authorized_job_events_event_id_seq TO cano_ci_restricted")
    with psycopg.connect(RUNTIME) as conn:
        for table in TABLES:
            assert conn.execute(f"SELECT count(*) FROM public.{table}").fetchone()[0] == 0
        conn.execute("SELECT set_config('cano.owner_key', %s, true)", (a,))
        for table in TABLES:
            assert conn.execute(f"SELECT count(*) FROM public.{table}").fetchone()[0] == 1
    print("QUEUE_RLS_FIXTURE_PASS", flush=True)
    qa = PostgresAuthorizedQueue(RUNTIME, owner_key=a, allow_test_clock=True)
    qb = PostgresAuthorizedQueue(RUNTIME, owner_key=b, allow_test_clock=True)
    qb.verify_schema()
    try:
        job = qb.enqueue("first", "Synthetic queue RLS", approved=True)
    except psycopg.errors.InsufficientPrivilege:
        print("QUEUE_RLS_ADAPTER_RED: missing transaction owner context", flush=True)
        raise
    assert qb.enqueue("first", "Synthetic queue RLS", approved=True)["id"] == job["id"]
    assert [r["id"] for r in qa.list()] == [seed["id"]]
    assert [r["id"] for r in qb.list()] == [job["id"]]
    try:
        qa.get(job["id"])
    except KeyError:
        pass
    else:
        raise AssertionError("Cross-owner queue read allowed")
    lease = qb.claim("worker", approved=True, now=100, lease_seconds=30)
    assert lease["id"] == job["id"]
    assert qb.claim("other-worker", approved=True, now=101) is None
    try:
        qa.complete(job["id"], lease["lease_token"], "Cross-owner", now=101)
    except KeyError:
        pass
    else:
        raise AssertionError("Cross-owner queue completion allowed")
    assert qb.complete(job["id"], lease["lease_token"], "Synthetic draft", now=101)["status"] == "review_pending"
    assert qb.get(job["id"])["draft"] == "Synthetic draft"
    assert [e["state"] for e in qb.events(job["id"])] == ["queued", "running", "review_pending"]
    expired = qb.enqueue("expired", "Synthetic expiry", approved=True)
    assert qb.claim("worker", approved=True, now=200, lease_seconds=5)["id"] == expired["id"]
    assert qb.recover_expired(now=205) == 1
    assert qb.get(expired["id"])["state"] == "blocked"
    assert qa.get(seed["id"])["state"] == "queued"
    with psycopg.connect(RUNTIME) as conn:
        for table in TABLES:
            assert conn.execute(f"SELECT count(*) FROM public.{table}").fetchone()[0] == 0
    print("QUEUE_RLS_ADAPTER_PASS: owner operations, approval, lease, expiry and event readback")
    print("SCOPE: direct authenticated queue only; local HTTP capability path needs separate policy design")


if __name__ == "__main__":
    main()
