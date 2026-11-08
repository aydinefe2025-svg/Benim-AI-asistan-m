"""Disposable PG17/18 CANO recovery comparison: no production connections.

Exercised only by the GitHub synthetic PostgreSQL CI service.
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from scripts.cano_dr_compare import TABLES, audit_application_restore


def run():
    source_url = os.getenv("TEST_DATABASE_URL", "")
    parsed = urlsplit(source_url)
    if (os.getenv("GITHUB_ACTIONS") != "true"
            or os.getenv("CANO_CI_ALLOW_DISPOSABLE_DB") != "1"
            or parsed.scheme not in ("postgres", "postgresql")
            or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.username != "ci_user" or parsed.port != 5432
            or parsed.path != "/ci_persistence" or parsed.query or parsed.fragment):
        raise RuntimeError("Refusing database outside synthetic GitHub CI service")
    import psycopg
    from psycopg import sql
    with psycopg.connect(source_url) as db:
        assert db.execute("SELECT current_database()").fetchone()[0] == "ci_persistence"
        major = str(int(db.execute("SHOW server_version_num").fetchone()[0]) // 10000)
        assert major == os.environ["CANO_CI_PG_MAJOR"]

    suffix = uuid4().hex[:9]
    source = "cano_ci_compare_" + suffix
    target = "cano_restore_compare_" + suffix

    def connection(dbname):
        return urlunsplit((parsed.scheme, parsed.netloc, "/" + dbname, "", ""))

    created = []
    with psycopg.connect(source_url, autocommit=True) as admin:
        try:
            for name in (source, target):
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
                created.append(name)
            for name in (source, target):
                with psycopg.connect(connection(name)) as db:
                    for table in TABLES:
                        db.execute(sql.SQL("""CREATE TABLE public.{} (
                            id text NOT NULL PRIMARY KEY,
                            data jsonb NOT NULL)""").format(sql.Identifier(table)))
                        db.execute(sql.SQL("""INSERT INTO public.{} (id, data)
                            VALUES ('a', %s::jsonb), ('b', %s::jsonb)""").format(
                            sql.Identifier(table)), (
                                json.dumps({"synthetic": "A", "table": table}),
                                json.dumps({"synthetic": "B", "table": table}),
                            ))
            from unittest.mock import patch
            with patch.dict(os.environ, {"CANO_DATABASE_URL": connection(source),
                                         "DATABASE_URL": connection(source)}):
                verified = audit_application_restore(connection(source), connection(target))
                assert verified["status"] == "MATCH"
                assert verified["verified_tables"] == len(TABLES)
                assert verified["rows_source"] == verified["rows_target"] == len(TABLES) * 2
                with psycopg.connect(connection(target)) as db:
                    db.execute("""UPDATE public.organism_lab_records
                        SET data = '{"synthetic":"changed","table":"organism_lab_records"}'::jsonb
                        WHERE id = 'b'""")
                unequal = audit_application_restore(connection(source), connection(target))
                assert unequal["status"] == "DIFFERENT"
                assert unequal["rows_source"] == unequal["rows_target"]
                assert unequal["mismatched_tables"] == ["organism_lab_records"]
                with psycopg.connect(connection(target)) as db:
                    db.execute("""UPDATE public.organism_lab_records
                        SET data = '{"synthetic":"B","table":"organism_lab_records"}'::jsonb
                        WHERE id = 'b'""")
                    db.execute("""CREATE INDEX synthetic_extra_index
                        ON public.organism_lab_records (id, data)""")
                structural = audit_application_restore(connection(source), connection(target))
                assert structural["status"] == "DIFFERENT"
                assert structural["schema_metadata_equal"] is False
                assert structural["mismatched_tables"] == []
                for bad in (connection(source), source_url):
                    try:
                        audit_application_restore(connection(source), bad)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("Unsafe target accepted")
            print(json.dumps({"status": "PASS", "pg_major": major,
                              "synthetic_tables": len(TABLES),
                              "synthetic_rows": len(TABLES)*2,
                              "matching_rows_detected": True,
                              "same_counts_different_lab_data_rejected": True,
                              "index_schema_change_rejected": True,
                              "live_source_alias_rejected": True,
                              "production_data_used": False}, sort_keys=True))
        finally:
            for name in reversed(created):
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    sql.Identifier(name)))


if __name__ == "__main__":
    run()
