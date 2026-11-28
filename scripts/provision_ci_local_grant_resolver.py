"""Install candidate resolver only on disposable CI PG17/18; no live migration."""
import os
from pathlib import Path
import psycopg

ADMIN = "postgresql://ci_user:synthetic-ci-only@localhost:5432/ci_persistence"
RUNTIME = "postgresql://cano_ci_restricted:synthetic-role-only@localhost:5432/ci_persistence"

def main():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("TEST_DATABASE_URL") != ADMIN:
        raise SystemExit("Disposable CI database required")
    with psycopg.connect(ADMIN) as conn:
        conn.execute(Path(__file__).with_name("cano_local_grant_owner_resolver.sql").read_text())
        conn.execute("GRANT EXECUTE ON FUNCTION public.cano_resolve_local_grant_owner(text,text) TO cano_ci_restricted")
        assert conn.execute("SELECT has_function_privilege('public','public.cano_resolve_local_grant_owner(text,text)','EXECUTE')").fetchone()[0] is False
    with psycopg.connect(RUNTIME) as conn:
        assert conn.execute("SELECT public.cano_resolve_local_grant_owner(%s,%s)", ("0"*32, "local-http-ready:"+"0"*64)).fetchone()[0] is None
        assert conn.execute("SELECT count(*) FROM public.cano_authorized_jobs").fetchone()[0] == 0
    print("LOCAL_GRANT_RESOLVER_FIXTURE_PASS: no public execute; wrong capability denied; RLS default deny preserved")

if __name__ == "__main__":
    main()
