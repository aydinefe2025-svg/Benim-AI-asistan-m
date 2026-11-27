"""Disposable PostgreSQL CI: real memory and task adapter owner-context regression."""
import os
import psycopg
from core.postgres_memory import PostgresMemoryStore
from core.postgres_task_store import PostgresTaskStore

ADMIN = "postgresql://ci_user:synthetic-ci-only@localhost:5432/ci_persistence"
RUNTIME = "postgresql://cano_ci_restricted:synthetic-role-only@localhost:5432/ci_persistence"
TABLES = ("private_memory_entries", "agent_research_tasks", "agent_research_task_events", "agent_research_drafts")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("TEST_DATABASE_URL") != ADMIN:
        raise SystemExit("Disposable CI database required")
    PostgresMemoryStore(ADMIN).initialize()
    PostgresTaskStore(ADMIN, "ci-rls-admin").initialize()
    with psycopg.connect(ADMIN) as conn:
        for table in TABLES:
            conn.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            conn.execute(f"""CREATE POLICY ci_owner_scope ON public.{table}
                FOR ALL TO cano_ci_restricted
                USING (owner_key = nullif(current_setting('cano.owner_key', true), ''))
                WITH CHECK (owner_key = nullif(current_setting('cano.owner_key', true), ''))""")
            conn.execute(f"GRANT SELECT, INSERT, UPDATE ON public.{table} TO cano_ci_restricted")
        conn.execute("GRANT USAGE ON SEQUENCE public.agent_research_task_events_event_id_seq TO cano_ci_restricted")
    a, b = "ci-rls-memory-task-a", "ci-rls-memory-task-b"
    entry = {"id": "ci-rls-entry", "text": "synthetic"}
    PostgresMemoryStore(ADMIN).save(a, entry)
    PostgresTaskStore(ADMIN, a).create("Synthetic seed")
    with psycopg.connect(RUNTIME) as conn:
        for table in TABLES:
            assert conn.execute(f"SELECT count(*) FROM public.{table}").fetchone()[0] == 0
        conn.execute("SELECT set_config('cano.owner_key', %s, true)", (a,))
        assert conn.execute("SELECT count(*) FROM private_memory_entries").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM agent_research_tasks").fetchone()[0] == 1
    print("MEMORY_TASK_RLS_FIXTURE_PASS", flush=True)
    failures = []
    memory = PostgresMemoryStore(RUNTIME)
    memory.verify_schema()
    try:
        memory.save(b, entry)
        assert memory.list(a) == [entry] and memory.list(b) == [entry]
        memory.save(b, {**entry, "text": "updated"})
        assert memory.list(a) == [entry]
        assert memory.list(b)[0]["text"] == "updated"
        print("MEMORY_RLS_ADAPTER_PASS")
    except psycopg.errors.InsufficientPrivilege:
        failures.append("memory")
        print("MEMORY_RLS_ADAPTER_RED: missing transaction owner context", flush=True)
    task_a, task_b = PostgresTaskStore(RUNTIME, a), PostgresTaskStore(RUNTIME, b)
    task_a.verify_schema()
    try:
        task = task_b.create("Synthetic RLS task")
        task_b.transition(task["id"], "running")
        task_b.finish_draft(task["id"], "Synthetic draft")
        assert task_b.load_draft(task["id"]) == "Synthetic draft"
        assert len(task_b.history(task["id"])) == 3
        assert task_b.get(task["id"])["status"] == "review_pending"
        assert len(task_b.list()) == 1
        assert len(task_a.list()) == 1
        try:
            task_a.get(task["id"])
        except KeyError:
            pass
        else:
            raise AssertionError("Cross-owner task read allowed")
        print("TASK_RLS_ADAPTER_PASS")
    except psycopg.errors.InsufficientPrivilege:
        failures.append("task")
        print("TASK_RLS_ADAPTER_RED: missing transaction owner context", flush=True)
    assert not failures, "Missing transaction context: " + ", ".join(failures)


if __name__ == "__main__":
    main()
