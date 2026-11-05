"""Opt-in integration test: actual pg_dump and pg_restore on an isolated CI database.

This test never connects to production; it requires a dedicated ephemeral
PostgreSQL service fixture and contains no production credentials.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from cano_pg_backup import make_backup, verify_backup


@unittest.skipUnless(os.getenv("CANO_PG_REHEARSAL") == "1", "Opt-in CI PostgreSQL service only")
class PostgreSQLRestoreRehearsal(unittest.TestCase):
    def _run(self, *arguments, database: str, text: bool = True):
        env = os.environ.copy()
        # Test connection data are supplied by CI; never use DATABASE_URL here.
        env.pop("DATABASE_URL", None)
        env.pop("AGENT_TASK_DATABASE_URL", None)
        env["PGDATABASE"] = database
        result = subprocess.run(
            arguments,
            env=env,
            check=False,
            capture_output=True,
            text=text,
            timeout=60,
        )
        if result.returncode:
            raise AssertionError(f"PostgreSQL test command failed: {arguments[0]} (exit {result.returncode})")
        return result.stdout.strip()

    def _query(self, db: str, sql: str) -> str:
        return self._run("psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql, database=db)

    def test_real_dump_restore_and_owner_data(self):
        source = "cano_ci_source"
        target = "cano_restore_rehearsal_" + uuid.uuid4().hex[:12]
        self.assertNotEqual(source, target)
        self.assertTrue(target.startswith("cano_restore_rehearsal_"))
        # Both database names are ephemeral and hard-coded by this CI test.
        # The service is freshly initialized by GitHub Actions.
        self._run("createdb", source, database="postgres")
        try:
            self._query(source, """
                CREATE TABLE private_memory_entries(
                    owner_key text NOT NULL,
                    entry_id text NOT NULL,
                    payload jsonb NOT NULL,
                    PRIMARY KEY(owner_key,entry_id));
                CREATE TABLE agent_research_tasks(
                    owner_key text NOT NULL,
                    id text NOT NULL,
                    status text NOT NULL,
                    evidence jsonb NOT NULL,
                    PRIMARY KEY(owner_key,id));
                INSERT INTO private_memory_entries VALUES
                    ('ownerA','one','{"note":"Türkçe ışık","seq":1}'::jsonb),
                    ('ownerB','two','{"note":"cell simulation only","seq":2}'::jsonb);
                INSERT INTO agent_research_tasks VALUES
                    ('ownerA','task1','review_pending','["doi:10.1/test","unverified"]'::jsonb),
                    ('ownerB','task2','planned','[]'::jsonb);
            """)
            expected_mem = self._query(source, "SELECT owner_key||'|'||entry_id||'|'||payload::text FROM private_memory_entries ORDER BY owner_key,entry_id")
            expected_tasks = self._query(source, "SELECT owner_key||'|'||id||'|'||status||'|'||evidence::text FROM agent_research_tasks ORDER BY owner_key,id")

            with tempfile.TemporaryDirectory() as tmp:
                # The fixture uses only the workflow's known disposable credentials.
                # An explicit URI protects the backup from ambient libpq account
                # inheritance while preserving the real dump/restore exercise.
                from urllib.parse import quote
                self.assertEqual(os.environ.get("PGUSER"), "cano_test")
                self.assertEqual(os.environ.get("PGPASSWORD"), "ephemeral_test_only")
                ci_url = ("postgresql://" + quote(os.environ["PGUSER"], safe="")
                          + ":" + quote(os.environ["PGPASSWORD"], safe="")
                          + "@localhost:5432/" + source)
                with patch.dict(os.environ, {"DATABASE_URL": ci_url}):
                    backup = make_backup(Path(tmp), database_env="DATABASE_URL")
                verified = verify_backup(Path(backup["receipt"]))
                self.assertEqual(verified["sha256"], backup["sha256"])
                self.assertFalse(verified["restored_to_new_database"])

                self._run("createdb", target, database="postgres")
                self._run(
                    "pg_restore", "--exit-on-error", "--no-owner", "--no-privileges",
                    "--single-transaction", "--dbname=" + target,
                    backup["archive"], database="postgres",
                )
                self.assertEqual(
                    self._query(target, "SELECT owner_key||'|'||entry_id||'|'||payload::text FROM private_memory_entries ORDER BY owner_key,entry_id"),
                    expected_mem,
                )
                self.assertEqual(
                    self._query(target, "SELECT owner_key||'|'||id||'|'||status||'|'||evidence::text FROM agent_research_tasks ORDER BY owner_key,id"),
                    expected_tasks,
                )
                self.assertEqual(self._query(target, "SELECT count(*) FROM private_memory_entries"), "2")
                self.assertEqual(self._query(target, "SELECT count(*) FROM agent_research_tasks"), "2")
                print("RESULT: synthetic PostgreSQL dump, SHA check, isolated restore, and owner-scoped data readback PASS")
        finally:
            if target.startswith("cano_restore_rehearsal_"):
                self._run("dropdb", "--if-exists", "--force", target, database="postgres")
            self._run("dropdb", "--if-exists", "--force", source, database="postgres")


if __name__ == "__main__":
    unittest.main()
