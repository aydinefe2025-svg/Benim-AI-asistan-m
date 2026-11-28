"""Disposable CI only: direct logins and transaction-bound proof on actual adapters."""
import json
import os
import secrets
from pathlib import Path
from scripts.check_postgres_authorized_queue import provision_synthetic_schema
import psycopg
from scripts.check_cano_production_role_matrix import ADMIN, MATRIX, PRIVS, SEQUENCES
from core.postgres_memory import PostgresMemoryStore
from core.postgres_task_store import PostgresTaskStore
from core.colony_postgres import ColonySnapshotStore
from core.postgres_authorized_queue import PostgresAuthorizedQueue
from core.postgres_local_grant import PostgresLocalGrant

ROLES = sorted({role for roles in MATRIX.values() for role in roles})
def url(role):
    assert role in ROLES
    return f"postgresql://{role}:synthetic-role-only@localhost:5432/ci_persistence"

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("TEST_DATABASE_URL") != ADMIN:
        raise SystemExit("Disposable CI database required")
    # Fresh service per version: no roles or policies inherited from other tests.
    PostgresMemoryStore(ADMIN).initialize()
    PostgresTaskStore(ADMIN, "ci-signed-fixture").initialize()
    ColonySnapshotStore(ADMIN).initialize()
    provision_synthetic_schema(ADMIN)
    keys = {role: secrets.token_hex(32) for role in ROLES}
    with psycopg.connect(ADMIN) as conn:
        conn.execute(Path(__file__).with_name("cano_local_grant_owner_resolver.sql").read_text())
        for role in ROLES:
            login_clause = "NOLOGIN" if role == "cano_snapshot_runtime" else "LOGIN PASSWORD 'synthetic-role-only'"
            conn.execute(f"CREATE ROLE {role} {login_clause} NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB")
            conn.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
        conn.execute("GRANT cano_snapshot_runtime TO cano_snapshot_app")
        provision_sql = Path(__file__).with_name("cano_owner_proof_provision_candidate.sql").read_text()
        conn.execute(provision_sql)
        # Existing schema/table/extension/function state must validate safely on a second run.
        conn.execute(provision_sql)
        assert conn.execute("SELECT NOT rolcanlogin FROM pg_roles WHERE rolname='cano_snapshot_runtime'").fetchone()[0]
        assert conn.execute("SELECT cano_context_proof.fixed_work_equal(decode(%s,'hex'),decode(%s,'hex'))",
                            ("ab"*32,"ab"*32)).fetchone()[0]
        assert not conn.execute("SELECT cano_context_proof.fixed_work_equal(decode(%s,'hex'),decode(%s,'hex'))",
                                ("ab"*32,"ac"+"ab"*31)).fetchone()[0]
        assert not conn.execute("SELECT cano_context_proof.fixed_work_equal(decode(%s,'hex'),decode(%s,'hex'))",
                                ("ab"*32,"ab"*31)).fetchone()[0]
        assert not conn.execute("SELECT cano_context_proof.fixed_work_equal(decode(%s,'hex'),decode(%s,'hex'))",
                                ("ab"*31,"ab"*31+"ac")).fetchone()[0]
        for role in ROLES:
            conn.execute("INSERT INTO cano_context_proof.signing_key VALUES (%s,%s)", (role, bytes.fromhex(keys[role])))
        for table, roles in MATRIX.items():
            for role, letters in roles.items():
                conn.execute(f"GRANT {','.join(PRIVS[x] for x in letters)} ON public.{table} TO {role}")
        for seq, roles in SEQUENCES.items():
            for role in roles:
                conn.execute(f"GRANT USAGE ON SEQUENCE public.{seq} TO {role}")
        conn.execute(Path(__file__).with_name("cano_signed_owner_cutover_candidate.sql").read_text())
        conn.execute(Path(__file__).with_name("cano_signed_owner_rollback_candidate.sql").read_text())
        assert conn.execute("SELECT count(*) FROM pg_policies WHERE policyname IN ('cano_owner_scope_v1','cano_owner_proof_v1')").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM cano_context_proof.signing_key").fetchone()[0] == 6
        conn.execute(Path(__file__).with_name("cano_signed_owner_cutover_candidate.sql").read_text())
        assert conn.execute("SELECT count(*) FROM pg_policies WHERE policyname IN ('cano_owner_scope_v1','cano_owner_proof_v1')").fetchone()[0] == 16
    with psycopg.connect(ADMIN) as conn:
        conn.execute("INSERT INTO private_memory_entries(owner_key,entry_id,payload) VALUES (%s,%s,%s::jsonb)", ("ci-unsigned-target","proof-seed",'{"id":"proof-seed","text":"synthetic"}'))
    with psycopg.connect(url("memory_runtime_app")) as conn:
        assert conn.execute("SELECT current_user=session_user").fetchone()[0]
        conn.execute("SELECT set_config('cano.owner_key',%s,true)",("ci-unsigned-target",))
        assert conn.execute("SELECT count(*) FROM private_memory_entries WHERE owner_key=%s",("ci-unsigned-target",)).fetchone()[0]==0
        assert not conn.execute("SELECT has_table_privilege(current_user,'cano_context_proof.signing_key','SELECT')").fetchone()[0]
    os.environ["CANO_OWNER_PROOF_MODE"]="required"
    os.environ["CANO_OWNER_PROOF_KEYS_JSON"]=json.dumps(keys)
    owner = "ci-signed-owner-a"
    other = "ci-signed-owner-b"
    mem = PostgresMemoryStore(url("memory_runtime_app"))
    mem.verify_schema()
    mem.save(owner, {"id":"signed-matrix", "text":"synthetic"})
    assert mem.list(owner) == [{"id":"signed-matrix", "text":"synthetic"}]
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

    with psycopg.connect(url("cano_snapshot_app")) as role_conn:
        role_conn.execute("SET ROLE cano_snapshot_runtime")
        assert role_conn.execute("SELECT current_user").fetchone()[0] == "cano_snapshot_runtime"
        role_conn.execute("RESET ROLE")

    print("SIGNED_REAL_ADAPTERS_PASS: dedicated direct login, memory, task, snapshot, queue, local capability, default deny")

    # Exercise real transaction reuse and key rotation with isolated synthetic
    # keys. Do not print a proof or key; both are sensitive even in diagnostics.
    from core.postgres_owner_proof import set_owner_context
    role = "memory_runtime_app"
    target = "ci-unsigned-target"
    old_env = {"CANO_OWNER_PROOF_MODE": "required",
               "CANO_OWNER_PROOF_KEYS_JSON": json.dumps(keys)}
    def visible(conn):
        return conn.execute("SELECT count(*) FROM public.private_memory_entries WHERE owner_key=%s", (target,)).fetchone()[0]
    def replay(conn, proof):
        conn.execute("SELECT set_config('cano.owner_key',%s,true), set_config('cano.owner_proof',%s,true)", (target, proof))
    with psycopg.connect(url(role)) as conn:
        pid = conn.execute("SELECT pg_backend_pid()").fetchone()[0]
        with conn.cursor() as cur:
            set_owner_context(cur, target, environment=old_env)
        assert visible(conn) == 1
        proof = conn.execute("SELECT current_setting('cano.owner_proof')").fetchone()[0]
        with psycopg.connect(url(role)) as other_conn:
            assert other_conn.execute("SELECT pg_backend_pid()").fetchone()[0] != pid
            replay(other_conn, proof)
            assert visible(other_conn) == 0
        conn.commit()
        assert conn.execute("SELECT pg_backend_pid()").fetchone()[0] == pid
        assert visible(conn) == 0
        replay(conn, proof)
        assert visible(conn) == 0
        with conn.cursor() as cur:
            set_owner_context(cur, target, environment=old_env)
        assert visible(conn) == 1
        conn.rollback()
        assert visible(conn) == 0
    new_key = secrets.token_hex(32)
    with psycopg.connect(ADMIN) as conn:
        conn.execute("UPDATE cano_context_proof.signing_key SET secret=%s WHERE role_name=%s", (bytes.fromhex(new_key), role))
    new_env = {"CANO_OWNER_PROOF_MODE": "required",
               "CANO_OWNER_PROOF_KEYS_JSON": json.dumps({**keys, role: new_key})}
    with psycopg.connect(url(role)) as conn:
        with conn.cursor() as cur:
            set_owner_context(cur, target, environment=old_env)
        assert visible(conn) == 0
        with conn.cursor() as cur:
            set_owner_context(cur, target, environment=new_env)
        assert visible(conn) == 1
        # A role-specific rotation must not grant access to another role's key.
        with conn.cursor() as cur:
            set_owner_context(cur, target, environment={
                "CANO_OWNER_PROOF_MODE": "required",
                "CANO_OWNER_PROOF_KEYS_JSON": json.dumps({role: keys["agent_task_app"]}),
            })
        assert visible(conn) == 0
    print("SIGNED_OWNER_REPLAY_ROTATION_PASS: distinct backend, reused backend after commit, rollback reset, old key rejected, new key accepted, wrong-role key rejected")


    # Planned rotation accepts a previous key only during a bounded overlap.
    # The existing immediate-revocation test above remains mandatory.
    next_key = secrets.token_hex(32)
    with psycopg.connect(ADMIN) as conn:
        conn.execute(Path(__file__).with_name("cano_owner_proof_rotation_candidate.sql").read_text())
        conn.execute("UPDATE cano_context_proof.signing_key SET previous_secret=secret, previous_valid_until=statement_timestamp()+interval '10 minutes', secret=%s WHERE role_name=%s",
                     (bytes.fromhex(next_key), role))
    next_env = {"CANO_OWNER_PROOF_MODE": "required",
                "CANO_OWNER_PROOF_KEYS_JSON": json.dumps({**keys, role: next_key})}
    def signed_visible(environment):
        with psycopg.connect(url(role)) as conn, conn.cursor() as cur:
            set_owner_context(cur, target, environment=environment)
            return visible(conn)
    assert signed_visible(new_env) == 1
    assert signed_visible(next_env) == 1
    assert signed_visible(old_env) == 0
    with psycopg.connect(ADMIN) as conn:
        conn.execute("UPDATE cano_context_proof.signing_key SET previous_valid_until=statement_timestamp()-interval '1 second' WHERE role_name=%s", (role,))
    assert signed_visible(new_env) == 0
    assert signed_visible(next_env) == 1
    with psycopg.connect(url(role)) as conn:
        assert not conn.execute("SELECT has_table_privilege(current_user,'cano_context_proof.signing_key','SELECT')").fetchone()[0]
    print("SIGNED_OWNER_BOUNDED_ROTATION_PASS: previous/current accepted, unrelated/expired rejected, registry private")


    # The already-RLS-enabled tables need additive restrictive policies, not
    # the eight-table rollback that disables RLS.
    with psycopg.connect(ADMIN) as conn:
        conn.execute("CREATE ROLE cano_autodev_worker NOLOGIN NOBYPASSRLS")
        conn.execute("CREATE TABLE public.cano_code_jobs (owner_key text NOT NULL,id text PRIMARY KEY,status text NOT NULL)")
        conn.execute("CREATE TABLE public.organism_lab_records (owner_key text NOT NULL,collection text NOT NULL,record_id text NOT NULL,payload jsonb NOT NULL,PRIMARY KEY(owner_key,collection,record_id))")
        conn.execute("INSERT INTO public.cano_code_jobs VALUES ('synthetic-a','a','queued'),('synthetic-b','b','queued')")
        conn.execute("INSERT INTO public.organism_lab_records VALUES ('synthetic-a','simulation','cano-organism-lab-v1-world-a','{}'),('synthetic-b','simulation','cano-organism-lab-v1-world-b','{}'),('synthetic-a','simulation','filesystem_snapshot_v1','{}'),('synthetic-b','simulation','filesystem_snapshot_v1','{}')")
        conn.execute("ALTER TABLE public.cano_code_jobs ENABLE ROW LEVEL SECURITY")
        conn.execute("ALTER TABLE public.organism_lab_records ENABLE ROW LEVEL SECURITY")
        conn.execute("GRANT SELECT,INSERT ON public.cano_code_jobs TO agent_task_app")
        conn.execute("GRANT SELECT,UPDATE ON public.cano_code_jobs TO cano_autodev_worker")
        conn.execute("GRANT SELECT,INSERT ON public.organism_lab_records TO cano_snapshot_app,cano_runtime_rw")
        conn.execute("GRANT SELECT,INSERT,UPDATE ON public.organism_lab_records TO organism_lab_runtime")
        conn.execute("CREATE POLICY cano_code_jobs_web_read ON public.cano_code_jobs FOR SELECT TO agent_task_app USING (owner_key=current_setting('cano.owner_key',true))")
        conn.execute("CREATE POLICY cano_code_jobs_web_insert ON public.cano_code_jobs FOR INSERT TO agent_task_app WITH CHECK (owner_key=current_setting('cano.owner_key',true))")
        conn.execute("CREATE POLICY cano_autodev_worker_select ON public.cano_code_jobs FOR SELECT TO cano_autodev_worker USING (owner_key='synthetic-a')")
        conn.execute("CREATE POLICY cano_autodev_worker_update ON public.cano_code_jobs FOR UPDATE TO cano_autodev_worker USING (owner_key='synthetic-a' AND status IN ('queued','running')) WITH CHECK (owner_key='synthetic-a' AND status IN ('running','pr_open','blocked'))")
        for app_role,label in (("cano_snapshot_app","cano_lab"),("cano_runtime_rw","cano_runtime")):
            pred = "owner_key=current_setting('cano.owner_key',true) AND collection='simulation' AND record_id LIKE 'cano-organism-lab-v1-%'"
            conn.execute(f"CREATE POLICY organism_lab_records_{label}_select ON public.organism_lab_records FOR SELECT TO {app_role} USING ({pred})")
            conn.execute(f"CREATE POLICY organism_lab_records_{label}_insert ON public.organism_lab_records FOR INSERT TO {app_role} WITH CHECK ({pred})")
        pred = "owner_key=current_setting('organism.owner_key',true) AND collection='simulation' AND record_id='filesystem_snapshot_v1'"
        conn.execute(f"CREATE POLICY organism_lab_runtime_snapshot_select ON public.organism_lab_records FOR SELECT TO organism_lab_runtime USING ({pred})")
        conn.execute(f"CREATE POLICY organism_lab_runtime_snapshot_insert ON public.organism_lab_records FOR INSERT TO organism_lab_runtime WITH CHECK ({pred})")
        conn.execute(f"CREATE POLICY organism_lab_runtime_snapshot_update ON public.organism_lab_records FOR UPDATE TO organism_lab_runtime USING ({pred}) WITH CHECK ({pred})")
    specs = (("agent_task_app","cano_code_jobs","cano.owner_key"),("cano_runtime_rw","organism_lab_records","cano.owner_key"),("cano_snapshot_app","organism_lab_records","cano.owner_key"),("organism_lab_runtime","organism_lab_records","organism.owner_key"))
    def check_extra(signed):
        for app_role,table,guc in specs:
            with psycopg.connect(url(app_role)) as conn, conn.cursor() as cur:
                cur.execute("SELECT set_config(%s,%s,true)",(guc,"synthetic-a"))
                cur.execute(f"SELECT count(*) FROM public.{table}")
                assert cur.fetchone()[0] == (0 if signed else 1)
                if signed:
                    set_owner_context(cur,"synthetic-a",environment=old_env)
                    cur.execute(f"SELECT owner_key FROM public.{table}")
                    assert cur.fetchall() == [("synthetic-a",)]
                    cur.execute("SELECT set_config(%s,%s,true)",(guc,"synthetic-b"))
                    cur.execute(f"SELECT count(*) FROM public.{table}")
                    assert cur.fetchone()[0] == 0
    check_extra(False)
    with psycopg.connect(ADMIN) as conn:
        conn.execute(Path(__file__).with_name("cano_remaining_signed_scope_candidate.sql").read_text())
    check_extra(True)
    with psycopg.connect(ADMIN) as conn:
        conn.execute("SET LOCAL ROLE cano_autodev_worker")
        assert conn.execute("SELECT owner_key FROM public.cano_code_jobs").fetchall() == [("synthetic-a",)]
        assert conn.execute("UPDATE public.cano_code_jobs SET status='running' WHERE id='a'").rowcount == 1
        assert conn.execute("UPDATE public.cano_code_jobs SET status='running' WHERE id='b'").rowcount == 0
        conn.execute("RESET ROLE")
        conn.execute(Path(__file__).with_name("cano_remaining_signed_scope_rollback.sql").read_text())
        assert conn.execute("SELECT count(*) FROM pg_class WHERE oid IN ('public.cano_code_jobs'::regclass,'public.organism_lab_records'::regclass) AND relrowsecurity").fetchone()[0] == 2
    check_extra(False)
    with psycopg.connect(ADMIN) as conn:
        conn.execute(Path(__file__).with_name("cano_remaining_signed_scope_candidate.sql").read_text())
    check_extra(True)
    print("SIGNED_REMAINING_TABLES_PASS: four direct login roles, worker fixed scope, rollback preserves original RLS")


if __name__=="__main__":
    main()
