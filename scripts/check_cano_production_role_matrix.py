"""Disposable CI: reproduce observed production role/table DML matrix, then test candidate RLS."""
import os
from pathlib import Path
import psycopg
from core.postgres_memory import PostgresMemoryStore
from core.postgres_task_store import PostgresTaskStore
from core.colony_postgres import ColonySnapshotStore
from core.postgres_authorized_queue import PostgresAuthorizedQueue
from core.postgres_local_grant import PostgresLocalGrant

ADMIN = "postgresql://ci_user:synthetic-ci-only@localhost:5432/ci_persistence"
ROLES = ("agent_task_app", "cano_runtime_rw", "cano_snapshot_app", "cano_snapshot_runtime", "memory_runtime_app", "organism_lab_runtime", "cano_autodev_worker")
MATRIX = {
    "agent_research_drafts": {
        "agent_task_app": "SIU",
        "cano_runtime_rw": "SIUD",
        "cano_snapshot_runtime": "SIUD"
    },
    "agent_research_task_events": {
        "agent_task_app": "SI",
        "cano_runtime_rw": "SIUD",
        "cano_snapshot_runtime": "SIUD"
    },
    "agent_research_tasks": {
        "agent_task_app": "SIU",
        "cano_runtime_rw": "SIUD",
        "cano_snapshot_runtime": "SIUD"
    },
    "cano_authorized_job_events": {
        "agent_task_app": "SI",
        "cano_runtime_rw": "SIUD",
        "cano_snapshot_runtime": "SIUD",
        "organism_lab_runtime": "SIUD"
    },
    "cano_authorized_jobs": {
        "agent_task_app": "SIU",
        "cano_runtime_rw": "SIUD",
        "cano_snapshot_runtime": "SIUD",
        "organism_lab_runtime": "SIUD"
    },
    "private_colony_snapshot_revisions": {
        "cano_runtime_rw": "SIUD",
        "cano_snapshot_app": "SI",
        "cano_snapshot_runtime": "SIUD",
        "organism_lab_runtime": "SIUD"
    },
    "private_colony_snapshots": {
        "cano_runtime_rw": "SIUD",
        "cano_snapshot_app": "SIU",
        "cano_snapshot_runtime": "SIUD"
    },
    "private_memory_entries": {
        "cano_runtime_rw": "SIUD",
        "cano_snapshot_runtime": "SIUD",
        "memory_runtime_app": "SIUD"
    }
}
PRIVS = {"S": "SELECT", "I": "INSERT", "U": "UPDATE", "D": "DELETE"}
SEQUENCES = {
    "agent_research_task_events_event_id_seq": MATRIX["agent_research_task_events"],
    "cano_authorized_job_events_event_id_seq": MATRIX["cano_authorized_job_events"],
    "private_colony_snapshot_revisions_revision_seq": MATRIX["private_colony_snapshot_revisions"],
}

def url(role):
    return f"postgresql://{role}:synthetic-role-only@localhost:5432/ci_persistence"

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("TEST_DATABASE_URL") != ADMIN:
        raise SystemExit("Disposable CI database required")
    with psycopg.connect(ADMIN) as conn:
        for role in ROLES:
            login = "NOLOGIN" if role in ("cano_snapshot_runtime", "cano_autodev_worker") else "LOGIN PASSWORD 'synthetic-role-only'"
            conn.execute(f"CREATE ROLE {role} {login} NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB")
            conn.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        for table, roles in MATRIX.items():
            for role, letters in roles.items():
                conn.execute(f"GRANT {','.join(PRIVS[x] for x in letters)} ON public.{table} TO {role}")
        for seq, roles in SEQUENCES.items():
            for role in roles:
                conn.execute(f"GRANT USAGE ON SEQUENCE public.{seq} TO {role}")
        conn.execute(Path(__file__).with_name("cano_owner_rls_candidate.sql").read_text())
        checks = 0
        for table, roles in MATRIX.items():
            for role in ROLES:
                for letter, priv in PRIVS.items():
                    actual = conn.execute("SELECT has_table_privilege(%s,%s,%s)", (role, "public."+table, priv)).fetchone()[0]
                    assert actual == (letter in roles.get(role, "")), (table, role, priv)
                    checks += 1
        assert checks == 224
    for role in ROLES:
        with psycopg.connect(ADMIN) as conn:
            conn.execute(f"SET LOCAL ROLE {role}")
            for table, roles in MATRIX.items():
                if "S" in roles.get(role, ""):
                    assert conn.execute("SELECT row_security_active(%s::regclass)", ("public."+table,)).fetchone()[0]
                    assert conn.execute(f"SELECT count(*) FROM public.{table}").fetchone()[0] == 0
    print("PRODUCTION_ROLE_MATRIX_PASS: 224 DML checks; all permitted table reads default deny under synthetic effective roles", flush=True)
    owner = "ci-matrix-owner-a"
    other = "ci-matrix-owner-b"
    mem = PostgresMemoryStore(url("memory_runtime_app"))
    mem.verify_schema()
    mem.save(owner, {"id":"matrix", "text":"synthetic"})
    assert mem.list(owner) == [{"id":"matrix", "text":"synthetic"}]
    assert mem.list(other) == []
    task = PostgresTaskStore(url("agent_task_app"), owner)
    task.verify_schema()
    job = task.create("Matrix task")
    task.transition(job["id"], "running")
    task.finish_draft(job["id"], "Synthetic matrix draft")
    assert task.load_draft(job["id"]) == "Synthetic matrix draft"
    assert PostgresTaskStore(url("agent_task_app"), other).list() == []
    snap = ColonySnapshotStore(url("cano_snapshot_app"))
    snap.verify_schema()
    payload = {"agents": [], "feedback": [], "reviews": []}
    assert snap.save_versioned_verified(owner, payload)
    assert snap.load(owner) == payload and snap.load(other) is None
    queue = PostgresAuthorizedQueue(url("agent_task_app"), owner_key=owner)
    queue.verify_schema()
    job = queue.enqueue("matrix", "Synthetic capability", approved=True)
    grant = PostgresLocalGrant.issue(queue, approved=True)
    assert grant["id"] == job["id"]
    assert PostgresLocalGrant(url("agent_task_app")).take(grant["grant"])["job_id"] == job["id"]
    assert PostgresLocalGrant.revoke(queue, job["id"], approved=True)["status"] == "blocked"
    print("DEDICATED_RUNTIME_MATRIX_PASS: memory, tasks, snapshots, queue, local capability")
    print("LIMIT: synthetic roles and candidate policy only; legacy role binding, deployment and independent review remain required")

if __name__ == "__main__":
    main()
