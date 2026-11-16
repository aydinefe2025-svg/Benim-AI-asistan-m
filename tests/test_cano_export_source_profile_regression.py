"""Fail-closed application source profile tests; no database or backup calls."""
import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from scripts import cano_cloud_encrypted_export as exp
from scripts import cano_backup_source_gate as gate
from scripts.cano_pg_backup import BackupError

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

class ApplicationProfilePreflightTests(unittest.TestCase):
    def _run_worker(self, profile):
        old = dict(exp._state)
        try:
            with tempfile.TemporaryDirectory() as temp:
                with patch.dict(os.environ, {**BASE, "CANO_REQUIRED_APPLICATION_PROFILE": profile}, clear=False), \
                     patch.object(exp, "_root", Path(temp)), \
                     patch.object(exp, "configured", return_value=True), \
                     patch.object(exp, "_source_table_count", return_value=1), \
                     patch.object(exp, "make_encrypted_backup") as dump:
                    exp._worker()
                    return dump.call_count, dict(exp._state)
        finally:
            exp._state.clear()
            exp._state.update(old)

    def test_missing_explicit_profile_rejected_before_dump(self):
        calls, state = self._run_worker("")
        self.assertEqual(0, calls)
        self.assertEqual("failed", state["phase"])

    def test_single_unrelated_table_not_enough_for_full_profile(self):
        calls, state = self._run_worker("full")
        self.assertEqual(0, calls)
        self.assertEqual("failed", state["phase"])

    def test_full_profile_rejects_non_cano_table_even_if_populated(self):
        def fake_run(args, **kwargs):
            return CompletedProcess(args, 0, stdout=(
                DB + "\tunrelated_table\t1\n").encode(), stderr=b"")
        with patch.object(gate.shutil, "which", return_value="psql"):
            with self.assertRaises(BackupError):
                exp._require_application_source(
                    environ={**BASE, "CANO_REQUIRED_APPLICATION_PROFILE": "full"},
                    runner=fake_run,
                )

    def test_full_profile_accepts_all_nine_tables_with_data(self):
        names = sorted(gate.APP_SOURCE_PROFILES["full"])
        seen = []
        required = gate.APP_SOURCE_PROFILES["full"]
        def fake_run(args, **kwargs):
            seen.append((args, kwargs))
            if "COUNT(*)" in args[-1]:
                return CompletedProcess(args, 0, stdout=(
                    DB + "\ttest\t" + ",".join(["3"] + ["0"] * (len(required)-1))
                    + "\n").encode(), stderr=b"")
            return CompletedProcess(args, 0, stdout=(
                DB + "\t" + ",".join(names) + "\t1\n").encode(), stderr=b"")
        with patch.object(gate.shutil, "which", return_value="psql"):
            result=exp._require_application_source(
                environ={**BASE, "CANO_REQUIRED_APPLICATION_PROFILE": "full"},
                runner=fake_run,
            )
        self.assertEqual(9, result["required_tables_matched"])
        self.assertEqual(2, len(seen))
        self.assertEqual(DB, seen[0][1]["env"]["PGDATABASE"])
        self.assertNotIn("CANO_RENDER_INTERNAL_URL", seen[0][1]["env"])
        proof = result["source_preflight"]
        self.assertEqual(9, proof["expected_table_count"])
        self.assertEqual(3, sum(proof["table_counts"].values()))
        self.assertEqual(64, len(proof["source_id_sha256"]))
        self.assertFalse(proof["live_app_env_binding_verified"])
        self.assertNotIn("placeholder", str(proof))
        self.assertNotIn("test", str(proof))
        self.assertTrue(all(call[1]["env"]["PGDATABASE"] == DB for call in seen))

    def test_profile_attestation_rejects_wrong_role_or_zero_scope(self):
        required = gate.APP_SOURCE_PROFILES["full"]
        names = sorted(required)
        for role, counts in [
            ("other", ["3"] + ["0"] * (len(required)-1)),
            ("test", ["0"] * len(required)),
            ("test", ["bogus"] + ["0"] * (len(required)-1)),
        ]:
            with self.subTest(role=role, count0=counts[0]):
                def fake_run(args, **kwargs):
                    if "COUNT(*)" in args[-1]:
                        return CompletedProcess(args, 0, stdout=(
                            DB + "\t" + role + "\t" + ",".join(counts) + "\n"
                        ).encode(), stderr=b"")
                    return CompletedProcess(args, 0, stdout=(
                        DB + "\t" + ",".join(names) + "\t1\n"
                    ).encode(), stderr=b"")
                with patch.object(gate.shutil, "which", return_value="psql"):
                    with self.assertRaises(BackupError):
                        exp._require_application_source(
                            environ={**BASE,
                                     "CANO_REQUIRED_APPLICATION_PROFILE": "full"},
                            runner=fake_run,
                        )

if __name__ == "__main__":
    unittest.main()
