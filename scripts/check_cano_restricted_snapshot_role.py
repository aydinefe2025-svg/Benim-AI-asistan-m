"""Disposable CI only: real PostgreSQL snapshot runtime without schema CREATE."""
import os
import psycopg
from core.colony_postgres import ColonySnapshotStore

ADMIN = "postgresql://ci_user:synthetic-ci-only@localhost:5432/ci_persistence"
RUNTIME = "postgresql://cano_ci_restricted:synthetic-role-only@localhost:5432/ci_persistence"

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("TEST_DATABASE_URL") != ADMIN:
        raise SystemExit("Disposable CI database required")
    ColonySnapshotStore(ADMIN).initialize()
    with psycopg.connect(ADMIN) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE ROLE cano_ci_restricted LOGIN PASSWORD 'synthetic-role-only' NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB")
            cur.execute("GRANT USAGE ON SCHEMA public TO cano_ci_restricted")
            cur.execute("GRANT SELECT, INSERT, UPDATE ON public.private_colony_snapshots TO cano_ci_restricted")
            cur.execute("GRANT SELECT, INSERT ON public.private_colony_snapshot_revisions TO cano_ci_restricted")
            cur.execute("GRANT USAGE ON SEQUENCE public.private_colony_snapshot_revisions_revision_seq TO cano_ci_restricted")
    with psycopg.connect(RUNTIME) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user, has_schema_privilege(current_user,'public','CREATE'), rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")
            assert cur.fetchone() == ("cano_ci_restricted", False, False, False)
            cur.execute("SELECT has_table_privilege(current_user,'public.private_colony_snapshots','TRUNCATE'), has_table_privilege(current_user,'public.private_colony_snapshots','DELETE')")
            assert cur.fetchone() == (False, False)
    try:
        with psycopg.connect(RUNTIME) as conn:
            conn.execute("CREATE TABLE public.cano_ci_forbidden_ddl (id integer)")
    except psycopg.errors.InsufficientPrivilege:
        pass
    else:
        raise AssertionError("Runtime role unexpectedly allowed DDL")
    store = ColonySnapshotStore(RUNTIME)
    store.verify_schema()
    a = {"agents": [], "feedback": [], "reviews": []}
    b = {**a, "agents": [{"id": "synthetic"}]}
    assert store.save_versioned_verified("ci-restricted-a", a)
    assert store.save_versioned_verified("ci-restricted-b", b)
    assert store.save_versioned_verified("ci-restricted-a", b, expected_prior=a)
    assert store.load("ci-restricted-a") == b
    assert store.load("ci-restricted-b") == b
    assert store.load("ci-restricted-missing") is None
    revisions = store.list_archived("ci-restricted-a")
    assert len(revisions) == 1
    assert store.load_archived("ci-restricted-a", revisions[0]["revision"]) == a
    assert store.load_archived("ci-restricted-b", revisions[0]["revision"]) is None
    # Explicit limitation: owner filtering here is application-level, not a
    # database RLS guarantee. Do not claim raw-SQL tenant isolation.
    with psycopg.connect(RUNTIME) as conn:
        count = conn.execute("SELECT count(*) FROM public.private_colony_snapshots WHERE owner_key IN ('ci-restricted-a','ci-restricted-b')").fetchone()[0]
        assert count == 2
    print("RESTRICTED_SNAPSHOT_ROLE_PASS: no schema CREATE, no DELETE/TRUNCATE, real DDL denied, schema verification, save, CAS, archive, readback, owner-filtered archive; shared runtime can read both synthetic owners, not RLS isolation")

if __name__ == "__main__":
    main()
