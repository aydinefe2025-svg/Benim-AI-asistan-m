"""CANO scheduled artifact restore: preserve continuity, never silently restart."""
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.cano_recover_colony_artifact import restore_previous_state


class ColonyArtifactRecoveryTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.target = self.root / "artifacts" / "colony-cycle.sqlite3"
        self.copies = []

    def valid_artifact(self, run_id=101, *, tick=3, report_run=None, report_ticks=None):
        folder = self.root / f"source-{run_id}"
        folder.mkdir(exist_ok=True)
        with sqlite3.connect(folder / "colony-cycle.sqlite3") as db:
            db.execute("CREATE TABLE colony_tick (tick_id INTEGER PRIMARY KEY, candidates TEXT, state TEXT)")
            for i in range(1, tick + 1):
                db.execute("INSERT INTO colony_tick VALUES(?, ?, 'proposed')", (i, "[]"))
        (folder / "colony-cycle.json").write_text(json.dumps({
            "github_run_id": str(run_id if report_run is None else report_run),
            "stored_ticks": tick if report_ticks is None else report_ticks,
            "verified_tick_id": tick,
            "db_integrity": "ok",
            "mode": "bounded_virtual_reproduction_with_held_out_validation",
            "specialist_agents": {"status": "passed"}
        }), encoding="utf-8")
        return folder

    @staticmethod
    def artifact(run_id, *, expired=False):
        return {"name": f"cano-colony-cycle-{run_id}",
                "expired": expired, "size_in_bytes": 4096}

    def fake_download(self, source):
        def download(run_id, name, dest):
            self.copies.append((run_id, name))
            shutil.copytree(source, dest, dirs_exist_ok=True)
        return download

    def test_skips_successful_freshness_only_run_and_restores_last_real_artifact(self):
        source = self.valid_artifact(run_id=101)
        calls = []
        def inspect(run_id):
            calls.append(run_id)
            return [] if run_id == 102 else [self.artifact(run_id)]
        result = restore_previous_state(
            self.target, run_ids=[102, 101], inspect_artifacts=inspect,
            download=self.fake_download(source))
        self.assertEqual(calls, [102, 101])
        self.assertEqual(self.copies, [(101, "cano-colony-cycle-101")])
        self.assertEqual(result["stored_ticks"], 3)
        self.assertEqual(result["last_tick_id"], 3)
        self.assertTrue(self.target.exists())

    def test_zero_valid_artifacts_fails_closed_without_creating_empty_state(self):
        with self.assertRaisesRegex(RuntimeError, "prior verified.*not found"):
            restore_previous_state(self.target, run_ids=[110, 109],
                                   inspect_artifacts=lambda _run_id: [],
                                   download=lambda *_: self.fail("should not download"))
        self.assertFalse(self.target.exists())

    def test_expired_artifact_is_skipped_without_silent_reset(self):
        source = self.valid_artifact(run_id=101)
        restored = restore_previous_state(
            self.target, run_ids=[102, 101],
            inspect_artifacts=lambda rid: [self.artifact(rid, expired=rid == 102)],
            download=self.fake_download(source))
        self.assertEqual(restored["stored_ticks"], 3)
        self.assertEqual(self.copies, [(101, "cano-colony-cycle-101")])

    def test_found_but_corrupt_artifact_never_falls_back_to_older_data(self):
        src = self.root / "corrupt"
        src.mkdir()
        (src / "colony-cycle.sqlite3").write_bytes(b"not a SQLite file")
        (src / "colony-cycle.json").write_text("{}", encoding="utf-8")
        with self.assertRaises((RuntimeError, sqlite3.DatabaseError, ValueError)):
            restore_previous_state(
                self.target, run_ids=[111, 101],
                inspect_artifacts=lambda rid: [self.artifact(rid)],
                download=self.fake_download(src))
        self.assertEqual(self.copies, [(111, "cano-colony-cycle-111")])
        self.assertFalse(self.target.exists())

    def test_receipt_run_identity_mismatch_rejected_without_history_rewind(self):
        source = self.valid_artifact(run_id=101, report_run=999)
        with self.assertRaisesRegex(RuntimeError, "receipt"):
            restore_previous_state(
                self.target, run_ids=[101],
                inspect_artifacts=lambda rid: [self.artifact(rid)],
                download=self.fake_download(source))
        self.assertFalse(self.target.exists())

    def test_receipt_tick_mismatch_rejected_without_creating_db(self):
        source = self.valid_artifact(run_id=101, report_ticks=99)
        with self.assertRaisesRegex(RuntimeError, "receipt"):
            restore_previous_state(
                self.target, run_ids=[101],
                inspect_artifacts=lambda rid: [self.artifact(rid)],
                download=self.fake_download(source))
        self.assertFalse(self.target.exists())

    def test_preexisting_valid_cache_is_reused_without_remote_calls(self):
        source = self.valid_artifact(run_id=101)
        self.target.parent.mkdir(parents=True)
        shutil.copy(source / "colony-cycle.sqlite3", self.target)
        def unreachable(*_):
            self.fail("Should not access remote when cache exists")
        result = restore_previous_state(
            self.target, run_ids=[], inspect_artifacts=unreachable, download=unreachable)
        self.assertEqual(result["stored_ticks"], 3)

    def test_preexisting_corrupt_cache_rejected(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"corrupted")
        with self.assertRaises((RuntimeError, sqlite3.DatabaseError, ValueError)):
            restore_previous_state(self.target, run_ids=[],
                                   inspect_artifacts=lambda _: [],
                                   download=lambda *_: None)
        self.assertEqual(self.target.read_bytes(), b"corrupted")

    def test_invalid_run_identifier_is_rejected_before_external_read(self):
        with self.assertRaises(ValueError):
            restore_previous_state(
                self.target, run_ids=[True],
                inspect_artifacts=lambda *_: self.fail("no external read"),
                download=lambda *_: self.fail("no download"))
        self.assertFalse(self.target.exists())

    def test_artifact_download_failure_does_not_create_empty_state(self):
        def broken_download(*_args):
            raise OSError("network interruption")
        with self.assertRaisesRegex(RuntimeError, "download"):
            restore_previous_state(
                self.target, run_ids=[101],
                inspect_artifacts=lambda rid: [self.artifact(rid)],
                download=broken_download)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
