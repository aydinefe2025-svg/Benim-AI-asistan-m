"""Disposable PG17/18: clean baseline -> owner RLS -> rollback -> reapply."""
import os
import re
from pathlib import Path
import psycopg
from core.postgres_memory import PostgresMemoryStore
from core.postgres_task_store import PostgresTaskStore
from core.colony_postgres import ColonySnapshotStore
from core.postgres_authorized_queue import PostgresAuthorizedQueue
from core.postgres_local_grant import PostgresLocalGrant
from scripts.check_postgres_authorized_queue import provision_synthetic_schema
from scripts.check_cano_production_role_matrix import ADMIN, MATRIX, ROLES, PRIVS, SEQUENCES, fixture_role

DB = "ci_owner_rls_rollback"
TARGET = ADMIN.rsplit("/", 1)[0] + "/" + DB
ROOT = Path(__file__).parent


def runtime(role):
    return f"postgresql://{fixture_role(role)}:synthetic-role-only@localhost:5432/{DB}"


def metadata(conn):
    return (
        conn.execute("SELECT relname, relrowsecurity, relforcerowsecurity, relacl::text FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind IN ('r','S') ORDER BY relname").fetchall(),
        conn.execute("SELECT tablename, policyname, roles, cmd, qual, with_check FROM pg_policies WHERE schemaname='public' ORDER BY tablename,policyname").fetchall(),
        conn.execute("SELECT to_regprocedure('public.cano_resolve_local_grant_owner(text,text)') IS NOT NULL").fetchone()[0],
    )


def digest(conn):
    conn.execute("SET LOCAL TIME ZONE 'UTC'")
    rows = {}
    for table in MATRIX:
        rows[table] = conn.execute(f"""SELECT count(*),
            encode(sha256(convert_to(coalesce(string_agg(h,',' ORDER BY h),''),'UTF8')),'hex')
            FROM (SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') AS h
            FROM public.{table} t) q""").fetchone()
    return rows


def apply(conn):
    conn.execute((ROOT/"cano_local_grant_owner_resolver.sql").read_text())
    candidate = (ROOT/"cano_owner_rls_candidate.sql").read_text()
    role_pattern = r"\b(?:" + "|".join(map(re.escape, ROLES)) + r")\b"
    conn.execute(re.sub(role_pattern, lambda m: fixture_role(m.group()), candidate))


def verify_scope(enabled):
    for role in ROLES:
        with psycopg.connect(TARGET) as conn:
            conn.execute(f"SET LOCAL ROLE {fixture_role(role)}")
            for table, roles in MATRIX.items():
                if "S" in roles.get(role, ""):
                    assert conn.execute("SELECT row_security_active(%s::regclass)", ("public."+table,)).fetchone()[0] == enabled
                    count = conn.execute(f"SELECT count(*) FROM public.{table}").fetchone()[0]
                    assert (count == 0 if enabled else count > 0), (role, table, count)


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("TEST_DATABASE_URL") != ADMIN:
        raise SystemExit("Disposable CI database required")
    with psycopg.connect(ADMIN, autocommit=True) as conn:
        conn.execute("CREATE DATABASE ci_owner_rls_rollback")
    PostgresMemoryStore(TARGET).initialize()
    PostgresTaskStore(TARGET, "ci-rb-a").initialize()
    ColonySnapshotStore(TARGET).initialize()
    provision_synthetic_schema(TARGET)
    for owner in ("ci-rb-a", "ci-rb-b"):
        PostgresMemoryStore(TARGET).save(owner, {"id":"seed", "text":"synthetic"})
        tasks = PostgresTaskStore(TARGET, owner)
        job = tasks.create("Synthetic task")
        tasks.transition(job["id"], "running")
        tasks.finish_draft(job["id"], "Synthetic draft")
        snap = ColonySnapshotStore(TARGET)
        first = {"agents":[], "feedback":[], "reviews":[]}
        second = {**first, "agents":[{"id":"seed"}]}
        assert snap.save_versioned_verified(owner, first)
        assert snap.save_versioned_verified(owner, second, expected_prior=first)
        PostgresAuthorizedQueue(TARGET, owner_key=owner).enqueue("seed", "Synthetic grant", approved=True)
    with psycopg.connect(TARGET) as conn:
        for role in ROLES:
            conn.execute(f"GRANT USAGE ON SCHEMA public TO {fixture_role(role)}")
        for table, roles in MATRIX.items():
            for role, letters in roles.items():
                conn.execute(f"GRANT {','.join(PRIVS[x] for x in letters)} ON public.{table} TO {fixture_role(role)}")
        for seq, roles in SEQUENCES.items():
            for role in roles:
                conn.execute(f"GRANT USAGE ON SEQUENCE public.{seq} TO {fixture_role(role)}")
        conn.execute("CREATE TABLE public.ci_unrelated_rls (id integer)")
        conn.execute("ALTER TABLE public.ci_unrelated_rls ENABLE ROW LEVEL SECURITY")
        conn.execute("CREATE POLICY ci_unrelated ON public.ci_unrelated_rls USING (false)")
        baseline = metadata(conn)
        baseline_data = digest(conn)
        assert len(baseline_data) == 8 and all(x[0] > 0 for x in baseline_data.values())
        assert not baseline[2] and [x[0] for x in baseline[1]] == ["ci_unrelated_rls"]
    verify_scope(False)
    with psycopg.connect(TARGET) as conn:
        apply(conn)
        assert digest(conn) == baseline_data
        active = metadata(conn)
        assert active[2] and len(active[1]) == 9
    verify_scope(True)
    q = PostgresAuthorizedQueue(runtime("agent_task_app"), owner_key="ci-rb-a")
    assert len(q.list()) == 1
    assert PostgresMemoryStore(runtime("memory_runtime_app")).list("ci-rb-a") == [{"id":"seed","text":"synthetic"}]
    # Inject failure within rollback transaction; metadata and data must survive.
    try:
        with psycopg.connect(TARGET) as conn:
            conn.execute((ROOT/"cano_owner_rls_rollback_candidate.sql").read_text())
            raise RuntimeError("injected rollback interruption")
    except RuntimeError as exc:
        assert str(exc) == "injected rollback interruption"
    with psycopg.connect(TARGET) as conn:
        assert metadata(conn) == active and digest(conn) == baseline_data
        conn.execute((ROOT/"cano_owner_rls_rollback_candidate.sql").read_text())
        assert metadata(conn) == baseline and digest(conn) == baseline_data
    verify_scope(False)
    assert len(q.list()) == 1
    with psycopg.connect(TARGET) as conn:
        apply(conn)
        assert metadata(conn) == active and digest(conn) == baseline_data
    verify_scope(True)
    print("OWNER_RLS_ROLLBACK_PASS: eight nonempty tables, exact catalog and row digest recovery, interrupted rollback atomic, unrelated policy preserved, reapply default deny")
    print("LIMIT: isolated synthetic database only; no live rollback or activation")

if __name__ == "__main__":
    main()
