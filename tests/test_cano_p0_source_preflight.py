"""Read-only P0 full-schema backup acceptance: no real database connections."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from cano_backup_source_gate import require_application_source


class FullP0SourcePreflightTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "PGHOST": "ep-cano.example.neon.tech",
            "PGDATABASE": "assistant_pg",
            "PGUSER": "backup_operator",
            "PGPASSWORD": "PRIVATE-SOURCE-PASSWORD",
            "CANO_BACKUP_KEY_HEX": "PRIVATE-NOT-A-PG-ENV",
        }

    @staticmethod
    def response(db="assistant_pg", tables=19, rows=113):
        return SimpleNamespace(
            returncode=0,
            stdout=f"{db}\t{tables}\t{rows}\n".encode("utf8"),
            stderr=b"",
        )

    def check(self, *, expected="113", response=None, env=None):
        spy = Mock(return_value=response or self.response())
        with patch("cano_backup_source_gate.shutil.which", return_value="/usr/bin/psql"):
            result = require_application_source(
                env or self.env,
                "p0_19",
                expected_host="ep-cano.example.neon.tech",
                expected_database="assistant_pg",
                expected_total_rows=expected,
                runner=spy,
            )
        return result, spy

    def test_full_19_table_113_row_preflight_returns_nonsecret_receipt(self):
        report, spy = self.check()
        self.assertEqual(report["profile"], "p0_19")
        self.assertEqual(report["required_tables_matched"], 19)
        self.assertEqual(report["expected_total_rows"], 113)
        self.assertTrue(report["row_count_verified"])
        self.assertTrue(report["source_host_pinned"])
        self.assertTrue(report["source_database_pinned"])
        self.assertIn("not", report["scope"].lower())
        self.assertNotIn("PRIVATE", str(report))
        call = spy.call_args
        command = call.args[0]
        self.assertEqual(command[1:4], ["-X", "--no-password", "-At"])
        sql = command[-1]
        self.assertEqual(sql.count("UNION ALL"), 18)
        self.assertIn('"public"."cano_code_jobs"', sql)
        self.assertIn('"cano_p0_neon_recovery_20261115"."private_memory_entries"', sql)
        self.assertIn("pg_catalog.pg_class", sql)
        self.assertIn("COUNT(*)", sql)
        self.assertNotIn("PRIVATE", str(command))
        self.assertNotIn("CANO_BACKUP_KEY_HEX", call.kwargs["env"])
        self.assertEqual(call.kwargs["env"]["PGPASSWORD"], "PRIVATE-SOURCE-PASSWORD")

    def test_p0_profile_missing_or_invalid_expected_rows_fails_before_psql(self):
        spy = Mock()
        with patch("cano_backup_source_gate.shutil.which", return_value="/usr/bin/psql"):
            for expected in (None, "", "0", "-1", "1e6", "113;DROP", " 113", True):
                with self.subTest(expected=expected):
                    with self.assertRaises(ValueError):
                        require_application_source(
                            self.env, "p0_19",
                            expected_host="ep-cano.example.neon.tech",
                            expected_database="assistant_pg",
                            expected_total_rows=expected,
                            runner=spy,
                        )
        spy.assert_not_called()

    def test_p0_profile_rejects_missing_extra_or_changed_source_counts(self):
        for tables, rows in ((18, 113), (20, 113), (19, 112), (19, 114)):
            with self.subTest(tables=tables, rows=rows):
                with self.assertRaises(ValueError):
                    self.check(response=self.response(tables=tables, rows=rows))

    def test_p0_profile_rejects_wrong_db_host_or_failed_psql(self):
        with self.assertRaises(ValueError):
            self.check(response=self.response(db="different_db"))
        bad_env = dict(self.env, PGHOST="wrong.example.net")
        with self.assertRaises(ValueError):
            self.check(env=bad_env)
        no_data = SimpleNamespace(returncode=1, stdout=b"", stderr=b"PRIVATE")
        with self.assertRaises(ValueError) as err:
            self.check(response=no_data)
        self.assertNotIn("PRIVATE", str(err.exception))

    def test_legacy_full_profile_still_does_not_require_new_count(self):
        tables = (
            "private_colony_snapshots,private_colony_snapshot_revisions,"
            "organism_lab_records,agent_research_tasks,"
            "agent_research_task_events,agent_research_drafts,"
            "cano_authorized_jobs,cano_authorized_job_events,"
            "private_memory_entries"
        )
        spy = Mock(return_value=SimpleNamespace(
            returncode=0, stdout=f"assistant_pg\t{tables}\t1\n".encode(),
            stderr=b"",
        ))
        with patch("cano_backup_source_gate.shutil.which", return_value="/usr/bin/psql"):
            value = require_application_source(
                self.env, "full",
                expected_host="ep-cano.example.neon.tech",
                expected_database="assistant_pg",
                runner=spy,
            )
        self.assertEqual(value["required_tables_matched"], 9)




class BackupEntryPointP0Tests(unittest.TestCase):
    def test_backup_cli_accepts_p0_profile(self):
        from unittest.mock import patch
        from cano_encrypted_backup import main
        with patch("sys.argv", [
            "cano_encrypted_backup.py", "backup", "unused",
            "--require-application-profile", "p0_19"
        ]), patch("cano_encrypted_backup.make_encrypted_backup", return_value={
            "encrypted": True
        }) as backup:
            self.assertEqual(main(), 0)
        self.assertEqual(backup.call_args.kwargs["source_profile"], "p0_19")

    def test_p0_backup_passes_explicit_expected_count_into_source_gate(self):
        import os
        import tempfile
        from unittest.mock import patch
        from cano_encrypted_backup import make_encrypted_backup, BackupError
        uri = "postgresql://operator:example@ep-cano.example.neon.tech/assistant_pg?sslmode=require"
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {
            "CANO_BACKUP_KEY_HEX": "11"*32, "DATABASE_URL": uri,
            "CANO_BACKUP_EXPECTED_HOST": "ep-cano.example.neon.tech",
            "CANO_BACKUP_EXPECTED_DB": "assistant_pg",
            "CANO_BACKUP_EXPECTED_TOTAL_ROWS": "113",
        }), patch("cano_encrypted_backup.require_application_source",
                  side_effect=ValueError("expected simulated gate failure")) as guard, \
             patch("cano_encrypted_backup.subprocess.Popen") as spawn:
            with self.assertRaisesRegex(BackupError, "source identity/inventory"):
                make_encrypted_backup(Path(td)/"backups",
                                     source_profile="p0_19",dump_bin=sys.executable)
            self.assertEqual(guard.call_args.kwargs["expected_total_rows"], "113")
            spawn.assert_not_called()
            self.assertFalse((Path(td)/"backups").exists())


class ArchiveWithoutReceiptVerificationTests(unittest.TestCase):
    """Authenticate a specific .canoenc without fabricating an old receipt."""

    def setUp(self):
        import hashlib, tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "orphan.canoenc"
        self.file.write_bytes(b"CANOENC1" + b"n" * 12 + b"encrypted-synthetic" + b"t" * 16)
        self.hash = hashlib.sha256(self.file.read_bytes()).hexdigest()

    def test_direct_archive_verification_authenticates_but_does_not_claim_restore(self):
        from cano_encrypted_backup import verify_encrypted_archive_direct
        proof = {
            "authenticated": True,
            "plaintext_sha256": "a" * 64,
            "plaintext_size_bytes": 128,
        }
        with patch("cano_encrypted_backup.decrypt_to_sink", return_value=proof) as check:
            result = verify_encrypted_archive_direct(self.file, expected_sha256=self.hash)
        check.assert_called_once_with(self.file, None)
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["ciphertext_sha256"], self.hash)
        self.assertFalse(result["source_identity_verified"])
        self.assertFalse(result["isolated_restore_verified"])
        self.assertFalse(result["receipt_authenticated"])
        self.assertNotIn("private", str(result).lower())

    def test_wrong_or_missing_pinned_hash_refuses_before_decrypt(self):
        from cano_encrypted_backup import verify_encrypted_archive_direct, BackupError
        for expected in ("", None, "f" * 64, "a" * 63, "g" * 64):
            with self.subTest(expected=str(expected)[:8]):
                with patch("cano_encrypted_backup.decrypt_to_sink") as check:
                    with self.assertRaises(BackupError):
                        verify_encrypted_archive_direct(self.file, expected_sha256=expected)
                    check.assert_not_called()

    def test_incorrect_magic_header_refuses_before_key_read(self):
        from cano_encrypted_backup import verify_encrypted_archive_direct, BackupError
        import hashlib
        self.file.write_bytes(b"NOTCANO!" + b"n" * 12 + b"x" * 25)
        actual = hashlib.sha256(self.file.read_bytes()).hexdigest()
        with patch("cano_encrypted_backup.decrypt_to_sink") as check:
            with self.assertRaises(BackupError):
                verify_encrypted_archive_direct(self.file, expected_sha256=actual)
            check.assert_not_called()

    def test_cli_direct_verify_only_does_not_require_receipt(self):
        from cano_encrypted_backup import main
        from unittest.mock import patch
        proof = {
            "authenticated": True,
            "plaintext_sha256": "b" * 64,
            "plaintext_size_bytes": 1024,
        }
        with patch("sys.argv", [
            "cano_encrypted_backup.py", "verify-archive", str(self.file),
            "--expected-sha256", self.hash,
        ]), patch("cano_encrypted_backup.decrypt_to_sink", return_value=proof), \
             patch("builtins.print") as out:
            self.assertEqual(main(), 0)
            result = "".join(str(c.args[0]) for c in out.call_args_list if c.args)
        self.assertIn('"authenticated": true', result)
        self.assertIn('"isolated_restore_verified": false', result)

    def test_cli_mismatched_hash_never_attempts_archive_authentication(self):
        from cano_encrypted_backup import main
        with patch("sys.argv", [
            "cano_encrypted_backup.py", "verify-archive", str(self.file),
            "--expected-sha256", "0" * 64,
        ]), patch("cano_encrypted_backup.decrypt_to_sink") as check:
            self.assertEqual(main(), 1)
            check.assert_not_called()

if __name__ == "__main__":
    unittest.main()
