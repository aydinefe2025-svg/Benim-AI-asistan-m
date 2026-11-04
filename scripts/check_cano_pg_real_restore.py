"""Real Postgres 16 pg_dump -> independent pg_restore CI acceptance.

Only synthetic, disposable GitHub Actions PostgreSQL data. Does NOT read Render
DATABASE_URL, change production databases, upload archives, or expose passwords.
The source and target DB names are deliberately different.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlsplit, urlunsplit

from scripts.cano_pg_backup import (BackupError, _libpq_env_from_url,
                                    make_backup, verify_backup)


def pg_env(url: str) -> dict[str, str]:
    # Exercise the same production connection parser as the real pg_dump tool.
    return _libpq_env_from_url(url)

def run_sql(url: str, statement: str) -> str:
    process = subprocess.run(
        ["psql", "-X", "-q", "-A", "-t", "-w", "-v", "ON_ERROR_STOP=1",
         "-c", statement],
        env=pg_env(url), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=45, check=False,
    )
    if process.returncode:
        raise AssertionError("Synthetic PostgreSQL SQL step failed")
    return process.stdout.decode("utf-8").strip()


def run():
    source = os.environ.get("TEST_DATABASE_URL", "")
    parts = urlsplit(source)
    if parts.path != "/ci_backup_source":
        raise AssertionError("Refusing to run against any non-CI source database")
    target = urlunsplit(parts._replace(path="/ci_backup_restore"))
    if source == target:
        raise AssertionError("Restore database must not equal source")
    # This named target exists only in the disposable Postgres GitHub CI service.
    run_sql(source, "CREATE DATABASE ci_backup_restore")
    run_sql(source, """
        CREATE SCHEMA cano_ci;
        CREATE TABLE cano_ci.research_jobs (
          owner_key text PRIMARY KEY, draft text NOT NULL
        );
        INSERT INTO cano_ci.research_jobs(owner_key,draft)
        VALUES ('synthetic-owner-a','synthetic-A'),
               ('synthetic-owner-b','synthetic-B');
    """)
    expected = "synthetic-owner-a:synthetic-A,synthetic-owner-b:synthetic-B"
    query = ("SELECT string_agg(owner_key || ':' || draft, ',' "
             "ORDER BY owner_key) FROM cano_ci.research_jobs")
    assert run_sql(source, query) == expected

    with tempfile.TemporaryDirectory(prefix="cano-pg-real-ci-") as temp:
        backup_dir = Path(temp) / "private-backup"
        receipt = make_backup(
            backup_dir, database_env="TEST_DATABASE_URL")
        archive = Path(receipt["archive"])
        assert archive.is_file()
        assert archive.stat().st_mode & 0o777 == 0o600
        readback = verify_backup(Path(receipt["receipt"]))
        assert readback["sha256"] == receipt["sha256"]
        assert readback["size_bytes"] == archive.stat().st_size
        # The backup tool correctly does not assert any restore on its own.
        assert not receipt["restored_to_new_database"]

        # Change source AFTER backup to prove the target reads an earlier snapshot.
        run_sql(source, """
            INSERT INTO cano_ci.research_jobs VALUES
            ('synthetic-owner-c','post-backup-only')
        """)
        assert run_sql(source, "SELECT COUNT(*) FROM cano_ci.research_jobs") == "3"
        restored = subprocess.run(
            ["pg_restore", "--exit-on-error", "--single-transaction",
             "--no-owner", "--no-privileges",
             "--dbname=ci_backup_restore", str(archive)],
            env=pg_env(target), stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, timeout=90, check=False,
        )
        if restored.returncode:
            raise AssertionError("Isolated pg_restore failed")
        assert run_sql(target, query) == expected
        assert run_sql(target, "SELECT COUNT(*) FROM cano_ci.research_jobs") == "2"
        assert run_sql(target, "SELECT current_database()") == "ci_backup_restore"

        # A modified archive must NOT pass receipt readback.
        with archive.open("ab") as stream:
            stream.write(b"synthetic-tamper")
        try:
            verify_backup(Path(receipt["receipt"]))
        except BackupError:
            pass
        else:
            raise AssertionError("Tampered PostgreSQL archive passed verification")

    print("REAL_PG16_DR: pg_dump archive verified, separate database restored, "
          "2/2 snapshot rows exact, post-backup third row excluded, "
          "tamper rejected, no Render data accessed")


if __name__ == "__main__":
    run()
