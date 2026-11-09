"""Synthetic fail-closed tests for operator-only multi-source rescue.

Never connects to user or production databases.
"""
from pathlib import Path
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.cano_encrypted_backup import BackupError
from scripts.cano_render_rescue import (
    _assert_private_destination_acl, backup_configured, main,
)


class RenderRescueCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / "private"
        self.first = "postgresql://owner:SECRET_A@localhost/cano_one?sslmode=require"
        self.second = "postgresql://owner:SECRET_B@localhost/cano_two?sslmode=require"
        self.env = {
            "CANO_BACKUP_KEY_HEX": "ab" * 32,
            "CANO_DATABASE_URL": self.first,
            "DATABASE_URL": self.first,
            "MEMORY_DATABASE_URL": self.second,
            "AGENT_TASK_DATABASE_URL": self.second,
        }

    def _mock_export(self, destination, *, database_env):
        folder = Path(destination)
        folder.mkdir(parents=True)
        archive = folder / "synthetic.canoenc"
        receipt = folder / "synthetic.receipt.json"
        archive.write_bytes(b"non-secret-test-only")
        receipt.write_text("{}", encoding="utf-8")
        return {"archive": str(archive), "receipt": str(receipt),
                "archive_sha256": "1" * 64}

    def test_all_configured_aliases_are_covered_once_per_identical_source(self):
        with patch.dict(os.environ, self.env, clear=True):
            with patch("scripts.cano_render_rescue.make_encrypted_backup",
                       side_effect=self._mock_export) as exporter:
                with patch("scripts.cano_render_rescue.verify_encrypted_backup",
                           return_value={"authenticated": True,
                                         "archive_sha256": "1" * 64,
                                         "plaintext_sha256": "2" * 64,
                                         "plaintext_size_bytes": 18}):
                    result = backup_configured(self.destination)
        self.assertEqual(exporter.call_count, 2)
        self.assertEqual(result["verified_source_count"], 2)
        self.assertEqual(result["covered_env_names"],
                         ["CANO_DATABASE_URL", "DATABASE_URL",
                          "MEMORY_DATABASE_URL", "AGENT_TASK_DATABASE_URL"])
        self.assertFalse(result["offsite_verified"])
        self.assertFalse(result["isolated_restore_verified"])
        manifest = self.destination / "cano-rescue-manifest.json"
        raw = manifest.read_text(encoding="utf-8")
        self.assertEqual(json.loads(raw)["verified_source_count"], 2)
        for secret in ("SECRET_A", "SECRET_B", "localhost", "cano_one", "cano_two"):
            self.assertNotIn(secret, raw)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o600)

    def test_real_synthetic_pgdump_streams_two_encrypted_archives(self):
        # Integration with actual AES-GCM streaming and two fake pg_dump
        # subprocesses. No database/user network access or private rows.
        from scripts.cano_encrypted_backup import (
            make_encrypted_backup as real_backup, verify_encrypted_backup as real_verify
        )
        fake = Path(self.temp.name) / "pg_dump_fake.py"
        fake.write_text("#!" + sys.executable + "\n"
                        "import os,sys\n"
                        "if '--version' in sys.argv:\n"
                        " print('pg_dump (PostgreSQL) 18.0')\n"
                        " raise SystemExit(0)\n"
                        "assert 'CANO_BACKUP_KEY_HEX' not in os.environ\n"
                        "assert os.environ.get('PGPASSWORD') in ('SECRET_A','SECRET_B')\n"
                        "sys.stdout.buffer.write(b'PGDMP-FAKE-' + "
                        "os.environ['PGDATABASE'].encode() * 200)\n",
                        encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        executable = str(fake)
        if os.name == "nt":
            wrapper = Path(self.temp.name) / "pg_dump_fake.cmd"
            wrapper.write_text('@echo off\r\n"' + sys.executable
                               + '" "' + str(fake) + '" %*\r\n')
            executable = str(wrapper)

        def use_fake(destination, *, database_env):
            return real_backup(destination, database_env=database_env,
                               dump_bin=executable)
        with patch.dict(os.environ, self.env):
            with patch("scripts.cano_render_rescue.make_encrypted_backup",
                       side_effect=use_fake):
                result = backup_configured(self.destination)
                self.assertEqual(result["verified_source_count"], 2)
                receipts = sorted(self.destination.glob("source-*/*.receipt.json"))
                self.assertEqual(len(receipts), 2)
                for receipt in receipts:
                    self.assertTrue(real_verify(receipt)["authenticated"])
        self.assertEqual(len(list(self.destination.glob("source-*/*.canoenc"))), 2)
        self.assertEqual(len(list(self.destination.rglob("*.dump"))), 0)

    def test_required_render_source_absent_fails_before_backup(self):
        """A verified Neon dump must not count as an expiring Render DB dump."""
        e = {**self.env,
             "CANO_REQUIRED_RENDER_DATABASE": "research_library_persistent_db",
             "CANO_REQUIRED_RENDER_HOST_PREFIX": "dpg-dbkfp5bm8hqs73bba7u0-a"}
        with patch.dict(os.environ, e, clear=True):
            with patch("scripts.cano_render_rescue.make_encrypted_backup",
                       side_effect=self._mock_export) as exporter:
                with patch("scripts.cano_render_rescue.verify_encrypted_backup",
                           return_value={"authenticated": True,
                                         "archive_sha256": "1" * 64}):
                    with self.assertRaises(BackupError):
                        backup_configured(self.destination)
                exporter.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_partial_render_identity_requirement_fails_closed(self):
        e = {**self.env,
             "CANO_REQUIRED_RENDER_DATABASE": "research_library_persistent_db"}
        with patch.dict(os.environ, e, clear=True):
            with self.assertRaises(BackupError):
                backup_configured(self.destination)
        self.assertFalse(self.destination.exists())

    def test_matching_render_source_is_covered_without_host_disclosure(self):
        render_url = (
            "postgresql://owner:SECRET_RENDER@"
            "dpg-dbkfp5bm8hqs73bba7u0-a.frankfurt-postgres.render.com/"
            "research_library_persistent_db?sslmode=require"
        )
        e = {**self.env, "DATABASE_URL": render_url,
             "CANO_REQUIRED_RENDER_DATABASE": "research_library_persistent_db",
             "CANO_REQUIRED_RENDER_HOST_PREFIX": "dpg-dbkfp5bm8hqs73bba7u0-a"}
        with patch.dict(os.environ, e, clear=True):
            with patch("scripts.cano_render_rescue.make_encrypted_backup",
                       side_effect=self._mock_export) as exporter:
                with patch("scripts.cano_render_rescue.verify_encrypted_backup",
                           return_value={"authenticated": True,
                                         "archive_sha256": "1" * 64}):
                    result = backup_configured(self.destination)
        self.assertEqual(result["verified_source_count"], 3)
        self.assertEqual(exporter.call_count, 3)
        self.assertEqual(result["required_render_source_numbers"], [2])
        manifest = (self.destination / "cano-rescue-manifest.json").read_text("utf-8")
        self.assertEqual(json.loads(manifest)["required_render_source_numbers"], [2])
        self.assertIn('"required_render_source_matched": true', manifest)
        self.assertNotIn("SECRET_RENDER", manifest)
        self.assertNotIn("dpg-dbkfp5bm8hqs73bba7u0-a", manifest)
        self.assertNotIn("research_library_persistent_db", manifest)

    def test_cli_requires_explicit_render_identity_before_export(self):
        """The operator CLI must never silently run in generic Neon-only mode."""
        with patch.dict(os.environ, self.env, clear=True):
            with patch.object(sys, "argv", ["cano_render_rescue",
                                            str(self.destination)]):
                with patch("scripts.cano_render_rescue.backup_configured",
                           return_value={"verified_source_count": 2}) as exporter:
                    self.assertEqual(main(), 1)
                    exporter.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_no_configured_urls_fails_before_writing(self):
        with patch.dict(os.environ, {"CANO_BACKUP_KEY_HEX": "ab" * 32},
                        clear=True):
            with self.assertRaises(BackupError):
                backup_configured(self.destination)
        self.assertFalse(self.destination.exists())

    def test_missing_backup_key_fails_before_writing(self):
        with patch.dict(os.environ, {
            "CANO_DATABASE_URL": self.first,
            "CANO_BACKUP_KEY_HEX": "invalid",
        }, clear=True):
            with self.assertRaises(BackupError):
                backup_configured(self.destination)
        self.assertFalse(self.destination.exists())

    def test_cannot_publish_success_on_second_export_failure(self):
        seen = []
        def fail_second(destination, *, database_env):
            seen.append(database_env)
            if len(seen) == 2:
                raise BackupError("synthetic second source failed")
            return self._mock_export(destination, database_env=database_env)
        with patch.dict(os.environ, self.env, clear=True):
            with patch("scripts.cano_render_rescue.make_encrypted_backup",
                       side_effect=fail_second):
                with patch("scripts.cano_render_rescue.verify_encrypted_backup",
                           return_value={"authenticated": True,
                                         "archive_sha256": "1" * 64}):
                    with self.assertRaises(BackupError):
                        backup_configured(self.destination)
        self.assertEqual(len(seen), 2, "second configured source must be attempted")
        self.assertFalse((self.destination / "cano-rescue-manifest.json").exists())

    def test_failed_authenticated_readback_never_publishes_manifest(self):
        with patch.dict(os.environ, {
            "CANO_BACKUP_KEY_HEX": "ab" * 32,
            "CANO_DATABASE_URL": self.first,
        }, clear=True):
            with patch("scripts.cano_render_rescue.make_encrypted_backup",
                       side_effect=self._mock_export):
                with patch("scripts.cano_render_rescue.verify_encrypted_backup",
                           return_value={"authenticated": False,
                                         "archive_sha256": "1" * 64}):
                    with self.assertRaises(BackupError):
                        backup_configured(self.destination)
        self.assertFalse((self.destination / "cano-rescue-manifest.json").exists())

    def test_refuses_ephemeral_render_web_service_storage(self):
        with patch.dict(os.environ, {
            "RENDER_SERVICE_ID": "srv-test",
            "CANO_DATABASE_URL": self.first,
            "CANO_BACKUP_KEY_HEX": "ab" * 32,
        }, clear=True):
            with self.assertRaises(BackupError):
                backup_configured(self.destination)
        self.assertFalse(self.destination.exists())

    def test_windows_rescue_destination_acl_fails_closed(self):
        with patch("scripts.cano_render_rescue._windows_private_acl", return_value=False) as acl:
            with self.assertRaisesRegex(BackupError, "private Windows ACL"):
                _assert_private_destination_acl(self.destination, windows=True)
        acl.assert_called_once_with(self.destination.parent)

    def test_windows_rescue_destination_acl_checks_existing_empty_target_too(self):
        self.destination.mkdir()
        with patch("scripts.cano_render_rescue._windows_private_acl", side_effect=[True, False]) as acl:
            with self.assertRaisesRegex(BackupError, "private Windows ACL"):
                _assert_private_destination_acl(self.destination, windows=True)
        self.assertEqual(acl.call_count, 2)
        self.assertEqual(acl.call_args_list[0].args[0], self.destination.parent)
        self.assertEqual(acl.call_args_list[1].args[0], self.destination)

    def test_cli_enforces_windows_acl_before_pg_dump_or_export(self):
        env = {**self.env,
               "CANO_REQUIRED_RENDER_DATABASE": "research_library_persistent_db",
               "CANO_REQUIRED_RENDER_HOST_PREFIX": "dpg-dbkfp5bm8hqs73bba7u0-a"}
        with patch.dict(os.environ, env, clear=True), patch.object(sys, "argv", ["cano_render_rescue", str(self.destination)]), patch("scripts.cano_render_rescue._assert_private_destination_acl", side_effect=BackupError("Unsafe private Windows ACL")) as acl, patch("scripts.cano_render_rescue._require_render_pg18_dump_client") as pg_dump, patch("scripts.cano_render_rescue.backup_configured") as exporter:
            self.assertEqual(main(), 1)
        acl.assert_called_once()
        pg_dump.assert_not_called()
        exporter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
