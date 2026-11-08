"""Real PostgreSQL 17/18 synthetic-only acceptance for isolated Lab v2 restore.

Creates and drops ONLY the cano_restore_lab_ci database inside the disposable
GitHub Actions Postgres service. Never accepts a remote database URL.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from urllib.parse import urlsplit, urlunsplit

from core.backup_encryption import encrypt_backup
from core.cano_backup_bundle import create_portable_bundle
from scripts.cano_lab_isolated_restore import restore_lab_archive

OWNER = "oidc_" + "a" * 64
PASSWORD = "synthetic-fixture-strong-password"


def record(tick: int, kind: str = "world") -> dict:
    raw = json.dumps({"simulation": True, "tick": tick}, sort_keys=True).encode()
    digest = hashlib.sha256(raw).hexdigest()
    return {"record_id": f"cano-organism-lab-v1-{kind}-{digest}",
            "kind": kind, "sha256": digest,
            "data_b64": base64.b64encode(raw).decode("ascii")}


def archive(records, *, v2=True) -> bytes:
    colony = {name: [] for name in ("agents", "feedback", "reviews", "missions")}
    return encrypt_backup(create_portable_bundle(
        colony=colony, memories=[], research_tasks=b"{}",
        authorized_queue=[], organism_records=records if v2 else None), PASSWORD)


def run() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CANO_CI_ALLOW_DISPOSABLE_DB") != "1":
        raise RuntimeError("Only disposable GitHub Actions synthetic database allowed")
    source = os.environ["TEST_DATABASE_URL"]
    parsed = urlsplit(source)
    if (parsed.scheme not in ("postgres", "postgresql")
            or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.path != "/ci_persistence" or parsed.username != "ci_user"
            or parsed.port != 5432):
        raise RuntimeError("Refusing a non-disposable source database")
    import psycopg
    from psycopg import sql

    target_db = "cano_restore_lab_ci"
    target = urlunsplit((parsed.scheme, parsed.netloc, "/" + target_db, parsed.query, ""))
    records = [record(1), record(2, "campaign"), record(3)]
    container = archive(records)

    with psycopg.connect(source, autocommit=True) as maintenance:
        assert maintenance.execute("SELECT current_database()").fetchone()[0] == "ci_persistence"
        assert os.environ.get("CANO_CI_PG_MAJOR") == str(
            maintenance.execute("SHOW server_version_num").fetchone()[0][:2])
        assert maintenance.execute(
            "SELECT COUNT(*) FROM pg_database WHERE datname = %s", (target_db,)
        ).fetchone()[0] == 0
        maintenance.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))
        try:
            with psycopg.connect(target) as db:
                db.execute("""CREATE TABLE public.organism_lab_records (
                    owner_key text NOT NULL,
                    collection text NOT NULL,
                    record_id text NOT NULL,
                    payload jsonb NOT NULL,
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (owner_key, collection, record_id)
                )""")
                db.execute("ALTER TABLE public.organism_lab_records ENABLE ROW LEVEL SECURITY")
                db.execute("""CREATE POLICY lab_owner ON public.organism_lab_records
                    USING (owner_key = current_setting('cano.owner_key', true))
                    WITH CHECK (owner_key = current_setting('cano.owner_key', true))""")

            outcome = restore_lab_archive(
                container, PASSWORD, database_url=target, owner_key=OWNER)
            assert outcome["restored_records"] == len(records)
            assert outcome["full_postgresql_restore"] is False
            with psycopg.connect(target) as db:
                rows = db.execute("""SELECT owner_key, collection, record_id,
                    payload ->> 'sha256'
                    FROM public.organism_lab_records ORDER BY record_id""").fetchall()
                assert len(rows) == len(records)
                assert {(row[2], row[3]) for row in rows} == {
                    (r["record_id"], r["sha256"]) for r in records}
                assert all(row[:2] == (OWNER, "simulation") for row in rows)

            for bad, password in [(container, "wrong-local-password"),
                                  (archive([], v2=False), PASSWORD)]:
                try:
                    restore_lab_archive(bad, password, database_url=target, owner_key=OWNER)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Rejected archive was accepted")
            try:
                restore_lab_archive(container, PASSWORD, database_url=target, owner_key=OWNER)
            except ValueError as error:
                assert "not empty" in str(error)
            else:
                raise AssertionError("Populated target accepted")
            # Enforce one synthetic INSERT failure after the first successful
            # INSERT to prove the entire destination transaction rolls back.
            bad_id = record(3)["record_id"]
            with psycopg.connect(target) as db:
                db.execute("DELETE FROM public.organism_lab_records")
                db.execute(sql.SQL("""ALTER TABLE public.organism_lab_records
                    ADD CONSTRAINT synthetic_reject_second CHECK (record_id <> {})""").format(
                    sql.Literal(bad_id)))
            try:
                restore_lab_archive(archive([record(1), record(3)]), PASSWORD,
                                    database_url=target, owner_key=OWNER)
            except psycopg.errors.CheckViolation:
                pass
            else:
                raise AssertionError("Synthetic transaction failure did not occur")
            with psycopg.connect(target) as db:
                assert db.execute("SELECT COUNT(*) FROM public.organism_lab_records").fetchone()[0] == 0
            print("PASS: real PG" + os.environ["CANO_CI_PG_MAJOR"]
                  + " encrypted v2 -> isolated lab, owner hash readback, wrong password,"
                    " v1 rejection, nonempty guard, atomic SQL rollback")
        finally:
            maintenance.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                sql.Identifier(target_db)))


if __name__ == "__main__":
    run()
