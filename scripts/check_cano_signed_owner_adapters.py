"""Disposable CI only: direct logins and transaction-bound proof on actual adapters."""
import json
import os
import secrets
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
    keys = {role: secrets.token_hex(32) for role in ROLES}
    with psycopg.connect(ADMIN) as conn:
        conn.execute("CREATE SCHEMA cano_context_proof_test")
        conn.execute("CREATE EXTENSION pgcrypto WITH SCHEMA cano_context_proof_test")
        conn.execute("CREATE TABLE cano_context_proof_test.signing_key (role_name text PRIMARY KEY, secret bytea NOT NULL)")
        conn.execute("""CREATE OR REPLACE FUNCTION cano_context_proof_test.verified_owner()
 RETURNS text
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'pg_temp'
AS $function$
DECLARE caller text; scoped_owner text; supplied text; signing_secret bytea; expected bytea; 
BEGIN
caller := CASE WHEN current_setting('role',true) IS NULL OR current_setting('role',true)='none' THEN session_user::text ELSE current_setting('role',true) END;
scoped_owner := current_setting('cano.owner_key',true);
supplied := current_setting('cano.owner_proof',true);
IF scoped_owner IS NULL OR scoped_owner !~ '^[a-zA-Z0-9_-]{1,128}$' OR supplied IS NULL OR supplied !~ '^[0-9a-f]{64}$' THEN RETURN NULL; END IF;
SELECT secret INTO signing_secret FROM cano_context_proof_test.signing_key WHERE role_name=caller;
IF signing_secret IS NULL THEN RETURN NULL; END IF;
expected := cano_context_proof_test.hmac(convert_to(caller||':'||scoped_owner||':'||pg_current_xact_id()::text||':'||pg_backend_pid()::text,'UTF8'),signing_secret,'sha256');
IF cano_context_proof_test.hmac(expected,signing_secret,'sha256') = cano_context_proof_test.hmac(decode(supplied,'hex'),signing_secret,'sha256') THEN RETURN scoped_owner; END IF;
RETURN NULL;
END $function$
""")
        conn.execute("REVOKE ALL ON FUNCTION cano_context_proof_test.verified_owner() FROM PUBLIC")
        for role in ROLES:
            conn.execute(f"CREATE ROLE {role} LOGIN PASSWORD 'synthetic-role-only' NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB")
            conn.execute(f"GRANT USAGE ON SCHEMA public,cano_context_proof_test TO {role}")
            conn.execute(f"GRANT EXECUTE ON FUNCTION cano_context_proof_test.verified_owner() TO {role}")
            conn.execute("INSERT INTO cano_context_proof_test.signing_key VALUES (%s,%s)", (role, bytes.fromhex(keys[role])))
        for table, roles in MATRIX.items():
            for role, letters in roles.items():
                conn.execute(f"GRANT {','.join(PRIVS[x] for x in letters)} ON public.{table} TO {role}")
            rolelist = ",".join(roles)
            conn.execute(f"CREATE POLICY ci_signed_scope ON public.{table} FOR ALL TO {rolelist} USING (owner_key=(SELECT cano_context_proof_test.verified_owner())) WITH CHECK (owner_key=(SELECT cano_context_proof_test.verified_owner()))")
            conn.execute(f"CREATE POLICY ci_signed_restrictive ON public.{table} AS RESTRICTIVE FOR ALL TO {rolelist} USING (owner_key=(SELECT cano_context_proof_test.verified_owner())) WITH CHECK (owner_key=(SELECT cano_context_proof_test.verified_owner()))")
        for seq, roles in SEQUENCES.items():
            for role in roles:
                conn.execute(f"GRANT USAGE ON SEQUENCE public.{seq} TO {role}")
        conn.execute("GRANT EXECUTE ON FUNCTION public.cano_resolve_local_grant_owner(text,text) TO agent_task_app")
    with psycopg.connect(ADMIN) as conn:
        conn.execute("INSERT INTO private_memory_entries(owner_key,entry_id,payload) VALUES (%s,%s,%s::jsonb)", ("ci-unsigned-target","proof-seed",'{"id":"proof-seed","text":"synthetic"}'))
    with psycopg.connect(url("memory_runtime_app")) as conn:
        assert conn.execute("SELECT current_user=session_user").fetchone()[0]
        conn.execute("SELECT set_config('cano.owner_key',%s,true)",("ci-unsigned-target",))
        assert conn.execute("SELECT count(*) FROM private_memory_entries WHERE owner_key=%s",("ci-unsigned-target",)).fetchone()[0]==0
        assert not conn.execute("SELECT has_table_privilege(current_user,'cano_context_proof_test.signing_key','SELECT')").fetchone()[0]
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

    print("SIGNED_REAL_ADAPTERS_PASS: dedicated direct login, memory, task, snapshot, queue, local capability, default deny")

if __name__=="__main__":
    main()
