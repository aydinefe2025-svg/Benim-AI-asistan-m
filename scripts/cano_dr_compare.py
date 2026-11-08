"""Read-only CANO source vs isolated full-PG-restore application-data audit.

Run on a trusted operator computer after an authenticated encrypted pg_dump
has been restored to a separate cano_restore_* PostgreSQL database.

Every row is SHA-256 hashed *inside PostgreSQL*. Only row digests, table names,
counts, and schema metadata leave the server. Database credentials, row contents
and account identifiers are never logged. The source and target are opened
read-only; no schema/data changes or exports occur.

This audit checks the nine known application tables and relevant table schema;
it does NOT by itself prove a full offsite encrypted backup or database-wide
roles/extensions/functions have been restored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

from scripts.cano_lab_isolated_restore import _connection_identity, _verify_target

TABLES = (
    "agent_research_drafts", "agent_research_task_events", "agent_research_tasks",
    "cano_authorized_job_events", "cano_authorized_jobs", "organism_lab_records",
    "private_colony_snapshot_revisions", "private_colony_snapshots", "private_memory_entries",
)
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _metadata(cur) -> str:
    """Hash object definitions; never read user rows at this stage."""
    allowed = list(TABLES)
    cur.execute("""SELECT table_name, ordinal_position, column_name, udt_name,
                   is_nullable, COALESCE(column_default, '')
                   FROM information_schema.columns
                   WHERE table_schema='public' AND table_name = ANY(%s::text[])
                   ORDER BY table_name, ordinal_position""", (allowed,))
    columns = cur.fetchall()
    if {item[0] for item in columns} != set(TABLES):
        raise ValueError("CANO recovery check is missing an expected application table")
    cur.execute("""SELECT rel.relname, con.conname, con.contype,
                   pg_get_constraintdef(con.oid)
                   FROM pg_constraint con
                   JOIN pg_class rel ON rel.oid=con.conrelid
                   JOIN pg_namespace n ON n.oid=rel.relnamespace
                   WHERE n.nspname='public' AND rel.relname=ANY(%s::text[])
                   ORDER BY rel.relname, con.conname""", (allowed,))
    constraints = cur.fetchall()
    cur.execute("""SELECT tablename, indexname, indexdef FROM pg_indexes
                   WHERE schemaname='public' AND tablename=ANY(%s::text[])
                   ORDER BY tablename, indexname""", (allowed,))
    indexes = cur.fetchall()
    cur.execute("""SELECT tablename, policyname, permissive::text, roles::text,
                   cmd, COALESCE(qual,''), COALESCE(with_check,'')
                   FROM pg_policies
                   WHERE schemaname='public' AND tablename=ANY(%s::text[])
                   ORDER BY tablename, policyname""", (allowed,))
    policies = cur.fetchall()
    cur.execute("""SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                   FROM pg_class c
                   JOIN pg_namespace n ON n.oid=c.relnamespace
                   WHERE n.nspname='public' AND c.relname=ANY(%s::text[])
                     AND c.relkind IN ('r','p')
                   ORDER BY c.relname""", (allowed,))
    flags = cur.fetchall()
    if {item[0] for item in flags} != set(TABLES):
        raise ValueError("CANO recovery object definitions are incomplete")
    data = json.dumps([columns, constraints, indexes, policies, flags],
                      ensure_ascii=False, sort_keys=True,
                      default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _snapshot(database_url, expected_database, *, connect):
    with connect(database_url, connect_timeout=8) as db, db.cursor() as cur:
        # A self-consistent snapshot and READ ONLY transaction prevent this
        # audit from changing any source or destination data.
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        cur.execute("SET LOCAL TIME ZONE 'UTC'")
        cur.execute("SELECT current_database()")
        row = cur.fetchone()
        if not row or row[0] != expected_database:
            raise ValueError("PostgreSQL connection resolved to an unexpected database")
        schema_digest = _metadata(cur)
        tables = {}
        for table in TABLES:  # table identifiers are fixed trusted literals
            cur.execute(
                "SELECT encode(sha256(convert_to(to_jsonb(r)::text, 'UTF8')), 'hex') "
                f"AS row_sha FROM public.{table} AS r ORDER BY row_sha")
            count = 0
            digest = hashlib.sha256()
            while True:
                batch = cur.fetchmany(512)
                if not batch:
                    break
                for item in batch:
                    if len(item) != 1 or not isinstance(item[0], str) or not _HASH.fullmatch(item[0]):
                        raise ValueError("Invalid PostgreSQL row-hash result")
                    digest.update(item[0].encode("ascii"))
                    count += 1
            tables[table] = {"rows": count, "digest": digest.hexdigest()}
        return {"schema": schema_digest, "tables": tables}


def audit_application_restore(source_url, target_url, *, connect=None):
    """Compare independent PostgreSQL snapshots; fail closed on unsafe target."""
    src = _connection_identity(source_url)
    dst_name = _verify_target(target_url)
    dst = _connection_identity(target_url)
    if src == dst or src[2] == dst_name:
        raise ValueError("Source and restore target must be distinct databases")
    if connect is None:
        import psycopg
        connect = psycopg.connect
    source = _snapshot(source_url, src[2], connect=connect)
    target = _snapshot(target_url, dst_name, connect=connect)
    changed = sorted(t for t in TABLES
                     if source["tables"][t] != target["tables"][t])
    schema_equal = source["schema"] == target["schema"]
    src_rows = sum(row["rows"] for row in source["tables"].values())
    dst_rows = sum(row["rows"] for row in target["tables"].values())
    matched = not changed and schema_equal
    return {
        "status": "MATCH" if matched else "DIFFERENT",
        "verified_tables": len(TABLES),
        "rows_source": src_rows,
        "rows_target": dst_rows,
        "schema_metadata_equal": schema_equal,
        "mismatched_tables": changed,
        "full_postgresql_disaster_recovery_verified": False,
        "notes": "Nine CANO table contents and metadata only; independent offsite backup receipt and full SQL object recovery require separate checks.",
    }


def main(argv=None) -> int:
    argparse.ArgumentParser(
        description="Read-only CANO application table comparison after isolated PostgreSQL restore").parse_args(argv)
    source_url = os.getenv("CANO_AUDIT_SOURCE_DATABASE_URL", "")
    target_url = os.getenv("CANO_RESTORE_DATABASE_URL", "")
    try:
        outcome = audit_application_restore(source_url, target_url)
    except Exception:
        # psycopg exceptions may contain credentials or private row values.
        # Never print the exception text, SQL or a connection URL.
        print("BLOCKED: sources, target or record readback could not be verified", file=sys.stderr)
        return 3
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if outcome["status"] == "MATCH" else 2


if __name__ == "__main__":
    raise SystemExit(main())
