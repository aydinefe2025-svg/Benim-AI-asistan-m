"""Regression: do not export an empty source as a successful backup."""
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from scripts import cano_cloud_encrypted_export as exp
from scripts.cano_pg_backup import BackupError


class RealSourcePreflightTests(unittest.TestCase):
    def test_zero_user_tables_prevents_backup_before_file_creation(self):
        old = dict(exp._state)
        try:
            with tempfile.TemporaryDirectory() as folder:
                with patch.object(exp, "_root", Path(folder)), \
                     patch.object(exp, "configured", return_value=True), \
                     patch.object(exp, "_source_table_count", return_value=0), \
                     patch.object(exp, "make_encrypted_backup") as dump:
                    exp._worker()
                    dump.assert_not_called()
                    self.assertEqual("failed", exp._state["phase"])
        finally:
            exp._state.clear()
            exp._state.update(old)


PREFIX = "dpg-dbkfp5bm8hqs73bba7u0-a"
DB = "research_library_persistent_db"
BASE = {
    "CANO_REQUIRED_RENDER_DATABASE": DB,
    "CANO_REQUIRED_RENDER_HOST_PREFIX": PREFIX,
    "CANO_RENDER_INTERNAL_URL": (
        "postgresql://test:placeholder@"
        + PREFIX + ".frankfurt-postgres.render.com/" + DB
    ),
}


class SourceCatalogTests(unittest.TestCase):
    def test_only_pinned_source_and_read_only_catalog_query(self):
        observed = []

        def fake_run(args, **kw):
            observed.append((args, kw))
            return CompletedProcess(args, 0, stdout=b"3\n", stderr=b"")

        with patch.object(exp.shutil, "which", return_value="psql"):
            self.assertEqual(3, exp._source_table_count(environ=BASE, runner=fake_run))
        self.assertEqual(1, len(observed))
        args, kw = observed[0]
        self.assertIn("SELECT count(*)", args[-1])
        self.assertIn("pg_catalog.pg_class", args[-1])
        self.assertNotIn("placeholder", " ".join(args).lower())
        self.assertEqual("research_library_persistent_db", kw["env"]["PGDATABASE"])
        self.assertNotIn("CANO_RENDER_INTERNAL_URL", kw["env"])
        self.assertEqual(30, kw["timeout"])

    def test_wrong_source_refused_before_subprocess(self):
        def forbidden(*args, **kwargs):
            self.fail("Unexpected subprocess")

        with patch.object(exp.shutil, "which", side_effect=forbidden):
            with self.assertRaises(BackupError):
                exp._source_table_count(
                    environ={**BASE, "CANO_REQUIRED_RENDER_DATABASE": "wrong"},
                    runner=forbidden)

    def test_empty_invalid_or_failed_metadata_is_never_accepted(self):
        for rc, value in (
            (0, b"0\n"), (1, b"2\n"), (0, b"oops"), (0, b""),
            (0, b"2\n3\n"),
        ):
            with self.subTest(rc=rc, value=value):
                def fake_run(args, **kw):
                    return CompletedProcess(args, rc, stdout=value, stderr=b"")

                with patch.object(exp.shutil, "which", return_value="psql"):
                    if rc == 0 and value == b"0\n":
                        self.assertEqual(
                            0, exp._source_table_count(environ=BASE, runner=fake_run))
                    else:
                        with self.assertRaises(BackupError):
                            exp._source_table_count(
                                environ=BASE, runner=fake_run)
