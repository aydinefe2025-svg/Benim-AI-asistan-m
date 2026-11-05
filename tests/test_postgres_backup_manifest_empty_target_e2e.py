"""Real synthetic PostgreSQL 16/18: never restore into occupied target.

Guarded to the existing disposable GitHub restore rehearsal, with an isolated
source and target database. Does not connect to Render/Neon or use user records.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from urllib.parse import quote
from uuid import uuid4

from scripts.cano_pg_backup_manifest import (
    BackupError, create_backup, restore_to_isolated_test_db,
)


def _sql(database: str, statement: str) -> str:
    result = subprocess.run(
        ["psql", "--no-psqlrc", "--no-password", "-v", "ON_ERROR_STOP=1",
         "-X", "-At", "-d", database, "-c", statement],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, check=False, timeout=30,
    )
    if result.returncode != 0:
        raise AssertionError("Disposable synthetic PostgreSQL command failed")
    return result.stdout.decode("ascii").strip()


@unittest.skipUnless(os.environ.get("CANO_PG_REHEARSAL") == "1",
                     "real PostgreSQL rehearsal requires explicit synthetic CI")
class EmptyTargetRealPostgresTests(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("PGHOST") not in {"127.0.0.1", "localhost"}
                or os.environ.get("PGUSER") != "cano_test"
                or os.environ.get("PGPASSWORD") != "ephemeral_test_only"):
            raise RuntimeError("Refusing PostgreSQL test outside disposable localhost CI")
        tag = uuid4().hex[:10]
        self.source = "cano_src_" + tag
        self.target = "cano_dst_" + tag + "_cano_restore_test"
        self.created = []
        self.addCleanup(self._drop_disposable)
        for database in (self.source, self.target):
            _sql("postgres", "CREATE DATABASE " + database)
            self.created.append(database)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.archive = Path(self.directory.name) / "owner_synthetic.dump"

        def local_url(db):
            return ("postgresql://" + quote(os.environ["PGUSER"], safe="")
                    + ":" + quote(os.environ["PGPASSWORD"], safe="")
                    + "@127.0.0.1:5432/" + db + "?sslmode=disable")
        self.source_url = local_url(self.source)
        self.target_url = local_url(self.target)

    def _drop_disposable(self):
        for name in reversed(self.created):
            # Names here are built solely from a hexadecimal uuid.
            _sql("postgres", "DROP DATABASE IF EXISTS " + name + " WITH (FORCE)")

    def test_real_restore_refuses_populated_target_then_accepts_empty_target(self):
        _sql(self.source, "CREATE TABLE public.cano_fixture ("
                          "owner_key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        _sql(self.source, "INSERT INTO public.cano_fixture VALUES "
                          "('ci-owner-a','alpha'),('ci-owner-b','beta')")
        report = create_backup(self.archive, database_url=self.source_url)
        self.assertGreater(report["size_bytes"], 0)

        _sql(self.target, "CREATE TABLE public.do_not_modify (id INTEGER PRIMARY KEY)")
        _sql(self.target, "INSERT INTO public.do_not_modify VALUES (19)")
        with self.assertRaisesRegex(BackupError, "empty"):
            restore_to_isolated_test_db(
                self.archive, source_url=self.source_url, target_url=self.target_url)
        self.assertEqual(_sql(self.target, "SELECT id FROM public.do_not_modify"), "19")
        self.assertEqual(
            _sql(self.target, "SELECT to_regclass('public.cano_fixture') IS NULL"), "t")

        _sql(self.target, "DROP TABLE public.do_not_modify")
        result = restore_to_isolated_test_db(
            self.archive, source_url=self.source_url, target_url=self.target_url)
        self.assertTrue(result["restore_command_succeeded"])
        self.assertFalse(result["readback_verified"])
        self.assertEqual(
            _sql(self.target, "SELECT owner_key || ':' || payload "
                              "FROM public.cano_fixture ORDER BY owner_key"),
            "ci-owner-a:alpha\nci-owner-b:beta")

        # Prevent a second restore into a destination that is now occupied.
        with self.assertRaisesRegex(BackupError, "empty"):
            restore_to_isolated_test_db(
                self.archive, source_url=self.source_url, target_url=self.target_url)


if __name__ == "__main__":
    unittest.main()
