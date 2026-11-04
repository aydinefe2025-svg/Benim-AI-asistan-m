import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.cano_pg_backup_manifest import (
    BackupError, create_backup, verify_backup, restore_to_isolated_test_db,
    _libpq_env_from_uri,
)


SOURCE = "postgresql://example:private-password@postgres.example.test/live_db"
TEST = "postgresql://test:another-password@postgres.example.test/backup_cano_restore_test"


class FakePG:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def __call__(self, args, **kwargs):
        self.calls.append((list(args), kwargs["env"].copy()))
        if args[0] == "pg_dump" and self.fail != "pg_dump":
            Path(args[-1]).write_bytes(b"PGDMP" + b"test-private-contents")
        return SimpleNamespace(returncode=1 if args[0] == self.fail else 0)


class PostgresBackupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "backup.dump"

    def test_backup_is_private_complete_and_readback_checkable(self):
        runner = FakePG()
        report = create_backup(self.path, database_url=SOURCE, runner=runner)
        self.assertEqual(report["status"], "catalog_verified_not_restore_tested")
        self.assertTrue(self.path.exists())
        self.assertTrue(self.path.with_name("backup.dump.manifest.json").exists())
        self.assertEqual(verify_backup(self.path, runner=runner)["integrity_verified"], True)
        self.assertFalse(verify_backup(self.path, runner=runner)["restore_tested"])
        self.assertEqual(runner.calls[0][0][0], "pg_dump")
        self.assertEqual(runner.calls[0][1]["PGDATABASE"], "live_db")
        self.assertEqual(runner.calls[0][1]["PGHOST"], "postgres.example.test")
        self.assertEqual(runner.calls[0][1]["PGSSLMODE"], "require")
        self.assertNotIn("private-password", json.dumps(report))
        self.assertTrue(all("private-password" not in repr(args) for args, env in runner.calls))
        with self.assertRaises(FileExistsError):
            create_backup(self.path, database_url=SOURCE, runner=runner)

    def test_new_restore_host_never_inherits_prior_pg_credentials(self):
        previous = {
            "PGHOST": "render.internal", "PGDATABASE": "render_production",
            "PGUSER": "render_owner", "PGPASSWORD": "synthetic-render-secret",
            "PGPASSFILE": "/private/render-only-pgpass",
            "DATABASE_URL": "postgresql://render_owner:old-secret@render.internal/prod",
            "CANO_BACKUP_DATABASE_URL": "postgresql://old:old-secret@render.internal/prod",
            "CANO_RESTORE_TEST_DATABASE_URL": "postgresql://old:old-secret@render.internal/test",
        }
        result = _libpq_env_from_uri(
            "postgresql://neon.example.test/cano_cano_restore_test?sslmode=require",
            previous,
        )
        self.assertEqual(result["PGHOST"], "neon.example.test")
        self.assertEqual(result["PGDATABASE"], "cano_cano_restore_test")
        for name in ("PGUSER", "PGPASSWORD", "PGPASSFILE",
                     "DATABASE_URL", "CANO_BACKUP_DATABASE_URL",
                     "CANO_RESTORE_TEST_DATABASE_URL"):
            with self.subTest(name=name):
                self.assertNotIn(name, result,
                                 "A different PostgreSQL host inherited a previous secret")

    def test_explicit_target_credentials_do_not_inherit_other_pgpassfile(self):
        result = _libpq_env_from_uri(
            "postgresql://target_user:t%40rget@neon.example.test/cano_cano_restore_test",
            {"PGUSER": "render_owner", "PGPASSWORD": "old-secret",
             "PGPASSFILE": "/private/other-database-pgpass"},
        )
        self.assertEqual(result["PGUSER"], "target_user")
        self.assertEqual(result["PGPASSWORD"], "t@rget")
        self.assertNotIn("PGPASSFILE", result)

    def test_missing_source_refused_without_file(self):
        with self.assertRaises(BackupError):
            create_backup(self.path, database_url="", runner=FakePG())
        self.assertFalse(self.path.exists())

    def test_dump_failure_keeps_no_public_backup(self):
        with self.assertRaises(BackupError):
            create_backup(self.path, database_url=SOURCE, runner=FakePG(fail="pg_dump"))
        self.assertFalse(self.path.exists())
        self.assertFalse(self.path.with_name("backup.dump.manifest.json").exists())
        self.assertEqual(list(self.path.parent.glob(".cano-pg-*")), [])

    def test_invalid_catalog_keeps_no_public_backup(self):
        with self.assertRaises(BackupError):
            create_backup(self.path, database_url=SOURCE, runner=FakePG(fail="pg_restore"))
        self.assertFalse(self.path.exists())

    def test_checksum_tampering_is_rejected(self):
        runner = FakePG()
        create_backup(self.path, database_url=SOURCE, runner=runner)
        self.path.write_bytes(self.path.read_bytes() + b"malicious")
        with self.assertRaisesRegex(BackupError, "mismatch"):
            verify_backup(self.path, runner=runner)

    def test_live_target_and_unnamed_target_are_refused(self):
        runner = FakePG()
        create_backup(self.path, database_url=SOURCE, runner=runner)
        with self.assertRaises(BackupError):
            restore_to_isolated_test_db(
                self.path, source_url=SOURCE, target_url=SOURCE, runner=runner)
        with self.assertRaises(BackupError):
            restore_to_isolated_test_db(
                self.path, source_url=SOURCE,
                target_url="postgresql://host/production", runner=runner)

    def test_isolated_restore_requires_explicit_separate_database(self):
        runner = FakePG()
        create_backup(self.path, database_url=SOURCE, runner=runner)
        result = restore_to_isolated_test_db(
            self.path, source_url=SOURCE, target_url=TEST, runner=runner)
        self.assertTrue(result["restore_command_succeeded"])
        self.assertFalse(result["readback_verified"])
        restore_args, restore_env = runner.calls[-1]
        self.assertEqual(restore_args[0], "pg_restore")
        self.assertIn("--single-transaction", restore_args)
        self.assertNotIn(TEST, repr(restore_args))
        self.assertEqual(restore_env["PGDATABASE"], "backup_cano_restore_test")


if __name__ == "__main__":
    unittest.main()
