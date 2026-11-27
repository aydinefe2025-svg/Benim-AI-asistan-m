"""Disposable CI only: owner-context RLS integration regression (RED first)."""
import os
import psycopg
from core.colony_postgres import ColonySnapshotStore

ADMIN = "postgresql://ci_user:synthetic-ci-only@localhost:5432/ci_persistence"
RUNTIME = "postgresql://cano_ci_restricted:synthetic-role-only@localhost:5432/ci_persistence"


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("TEST_DATABASE_URL") != ADMIN:
        raise SystemExit("Disposable CI database required")
    # The preceding restricted-role step created both synthetic owners.
    with psycopg.connect(ADMIN) as conn:
        for table in ("private_colony_snapshots", "private_colony_snapshot_revisions"):
            conn.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            conn.execute(f"""CREATE POLICY ci_snapshot_owner_scope ON public.{table}
                FOR ALL TO cano_ci_restricted
                USING (owner_key = nullif(current_setting('cano.owner_key', true), ''))
                WITH CHECK (owner_key = nullif(current_setting('cano.owner_key', true), ''))""")
    with psycopg.connect(RUNTIME) as conn:
        assert conn.execute("SELECT count(*) FROM public.private_colony_snapshots").fetchone()[0] == 0
        conn.execute("SELECT set_config('cano.owner_key', %s, true)", ("ci-restricted-a",))
        assert conn.execute("SELECT count(*) FROM public.private_colony_snapshots WHERE owner_key='ci-restricted-a'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM public.private_colony_snapshots WHERE owner_key='ci-restricted-b'").fetchone()[0] == 0
    with psycopg.connect(RUNTIME) as conn:
        assert conn.execute("SELECT count(*) FROM public.private_colony_snapshots").fetchone()[0] == 0
    print("SYNTHETIC_RLS_FIXTURE_PASS: default deny and transaction-local owner filtering", flush=True)
    store = ColonySnapshotStore(RUNTIME)
    store.verify_schema()
    a = {"agents": [], "feedback": [], "reviews": []}
    b = {**a, "agents": [{"id": "synthetic-rls"}]}
    try:
        assert store.save_versioned_verified("ci-rls-owner-a", a)
    except psycopg.errors.InsufficientPrivilege:
        print("RLS_ADAPTER_RED: actual snapshot adapter lacks transaction owner context", flush=True)
        raise
    assert store.save_versioned_verified("ci-rls-owner-b", b)
    assert store.save_versioned_verified("ci-rls-owner-a", b, expected_prior=a)
    assert store.load("ci-rls-owner-a") == b
    assert store.load("ci-rls-owner-b") == b
    revs = store.list_archived("ci-rls-owner-a")
    assert len(revs) == 1
    assert store.load_archived("ci-rls-owner-a", revs[0]["revision"]) == a
    assert store.load_archived("ci-rls-owner-b", revs[0]["revision"]) is None
    print("SNAPSHOT_RLS_ADAPTER_PASS: scoped actual adapter operations; shared login can set GUC, not independent authentication")


if __name__ == "__main__":
    main()
