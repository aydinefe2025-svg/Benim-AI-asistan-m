"""Real disposable PostgreSQL acceptance for CANO's web code-job intake.

This deliberately tests persistent, owner-scoped queue creation, NOT a live
authenticated browser or a real autonomous worker/deployment. Synthetic only.
Never run against a production host, even if an environment variable points there.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg

from core.cano_code_jobs import CodeJobStore

ROOT = Path(__file__).resolve().parents[1]
OWNER_A = "oidc_" + "a" * 64
OWNER_B = "oidc_" + "b" * 64
GOAL = "Verify CANO code job isolation using disposable PostgreSQL"


def _disposable_only(database_url: str) -> None:
    host = urlsplit(database_url).hostname
    if (os.environ.get("GITHUB_ACTIONS", "").lower() != "true"
            or host not in {"localhost", "127.0.0.1"}):
        raise PermissionError("Code-job integration requires disposable local CI PostgreSQL")


def _app_connection(database_url: str):
    connection = psycopg.connect(database_url, connect_timeout=8)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE agent_task_app")
        return connection
    except BaseException:
        connection.close()
        raise


def run(database_url: str) -> dict:
    _disposable_only(database_url)
    # New GitHub Actions postgres service: a never-reused synthetic database.
    with psycopg.connect(database_url, connect_timeout=8) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname='agent_task_app'")
            if cursor.fetchone() is None:
                cursor.execute("CREATE ROLE agent_task_app NOLOGIN")
            cursor.execute(
                (ROOT / "scripts" / "provision_cano_code_jobs.sql").read_text(
                    encoding="utf-8"
                )
            )
            cursor.execute(
                "SELECT has_table_privilege('agent_task_app', "
                "'public.cano_code_jobs', 'UPDATE'), "
                "has_table_privilege('agent_task_app', "
                "'public.cano_code_jobs', 'DELETE')"
            )
            assert cursor.fetchone() == (False, False), "Web app can mutate code-job states"

    a = CodeJobStore(database_url, OWNER_A, connect=_app_connection)
    b = CodeJobStore(database_url, OWNER_B, connect=_app_connection)
    a.verify_schema()
    b.verify_schema()
    first = a.enqueue(GOAL)
    assert first["status"] == "queued" and not first["duplicate"], "First code job failed"
    duplicate = a.enqueue(GOAL)
    assert duplicate["duplicate"] and duplicate["id"] == first["id"], "Duplicate code job inserted"
    assert b.recent() == [], "Owner B saw owner A's job"
    other = b.enqueue(GOAL)
    assert other["status"] == "queued" and other["id"] != first["id"], "Other owner lost job"
    assert [item["id"] for item in a.recent()] == [first["id"]], "Owner A saw foreign job"
    assert [item["id"] for item in b.recent()] == [other["id"]], "Owner B saw foreign job"

    # Verify RLS also applies to raw SQL under the restricted web app role,
    # independently of CodeJobStore's owner-filtered query implementation.
    with _app_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('cano.owner_key', %s, true)", (OWNER_A,))
            cursor.execute(
                "SELECT count(*) FROM public.cano_code_jobs WHERE id::text=%s",
                (other["id"],),
            )
            assert cursor.fetchone()[0] == 0, "RLS leaked another owner's code job"

    rejected_foreign_insert = False
    try:
        with _app_connection(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('cano.owner_key', %s, true)", (OWNER_A,))
                cursor.execute(
                    "INSERT INTO public.cano_code_jobs(owner_key,goal_hash,goal) "
                    "VALUES(%s,%s,%s)",
                    (OWNER_B, "c" * 64, "Forbidden cross-owner code instruction"),
                )
    except psycopg.errors.InsufficientPrivilege:
        rejected_foreign_insert = True
    assert rejected_foreign_insert, "RLS accepted a cross-owner code job"

    # Verify committed rows are visible through a fresh privileged connection;
    # never print owner keys, connection strings or private records.
    with psycopg.connect(database_url, connect_timeout=8) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM public.cano_code_jobs "
                "WHERE id::text IN (%s,%s)",
                (first["id"], other["id"]),
            )
            assert cursor.fetchone()[0] == 2, "Committed job readback failed"

    return {
        "status": "verified",
        "database": "disposable_pg",
        "owner_rls_read": True,
        "owner_rls_insert": True,
        "web_role_state_mutation_denied": True,
        "repeat_submission_deduplicated": True,
        "fresh_connection_readback": True,
        "real_browser_submitted": False,
        "real_worker_executed": False,
        "production_data_mutated": False,
    }


if __name__ == "__main__":
    url = os.environ.get("TEST_TASK_DATABASE_URL", "")
    try:
        print(json.dumps(run(url), sort_keys=True))
    except Exception as exc:
        # Never include database credentials in logs, including driver errors.
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(1)
