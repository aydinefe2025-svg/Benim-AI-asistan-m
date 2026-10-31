"""Backup/restore tests against real SQLite files and research lineage."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.knowledge_store import KnowledgeStore
from core.notion_source_manifest import import_source_manifest
from core.sqlite_backup import backup_research_db, restore_research_db, backup_with_receipt, recovery_drill


class SQLiteBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source_path = self.root / "live.sqlite3"
        self.store = KnowledgeStore(self.source_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _seed(self):
        first = self.store.add_source(
            "https://example.org/first", "Original research", content="first version"
        )
        self.store.add_source(
            "https://example.org/first", "Original research", content="second version"
        )
        claim = self.store.add_claim("Testable hypothesis", [first["id"]])
        self.store.add_review_note(
            claim["id"], first["id"], reviewer_label="unverified-reviewer",
            assessment="needs_more_evidence", rationale="No control group",
        )
        import_source_manifest(self.store, [{
            "research_id": "D2026-001", "url": "https://example.org/first",
            "title": "Original research", "notion_page_id": "notion-original",
        }])
        return first, claim

    def test_backup_restores_sources_claims_reviews_revisions_and_notion_links(self):
        first, claim = self._seed()
        backup_path = self.root / "snapshot.sqlite3"
        result = backup_research_db(self.source_path, backup_path)
        self.assertTrue(backup_path.is_file())
        self.assertEqual(result["integrity_check"], "ok")
        self.assertEqual(result["source_count"], 1)
        self.assertEqual(result["claim_count"], 1)
        dest_path = self.root / "restored.sqlite3"
        restore = restore_research_db(backup_path, dest_path)
        self.assertEqual(restore["integrity_check"], "ok")
        restored = KnowledgeStore(dest_path)
        self.assertEqual(restored.list_sources(), self.store.list_sources())
        self.assertEqual(restored.list_claims(), self.store.list_claims())
        self.assertEqual(restored.list_review_notes(claim["id"]),
                         self.store.list_review_notes(claim["id"]))
        self.assertEqual(restored.list_revisions(first["id"]),
                         self.store.list_revisions(first["id"]))
        self.assertEqual(restored.list_source_manifest_links(),
                         self.store.list_source_manifest_links())

    def test_backup_exposes_digest_for_out_of_band_verification(self):
        import hashlib
        self._seed()
        backup = self.root / "verified.sqlite3"
        result = backup_research_db(self.source_path, backup)
        actual = hashlib.sha256(backup.read_bytes()).hexdigest()
        self.assertEqual(result["sha256"], actual)
        self.assertEqual(len(actual), 64)
        restored = restore_research_db(
            backup, self.root / "verified-restore.sqlite3",
            expected_sha256=result["sha256"],
        )
        self.assertEqual(restored["sha256"], actual)

    def test_digest_mismatch_detects_modified_but_valid_sqlite(self):
        self._seed()
        backup = self.root / "snapshot.sqlite3"
        recorded = backup_research_db(self.source_path, backup)["sha256"]
        import sqlite3
        with sqlite3.connect(backup) as conn:
            conn.execute("UPDATE sources SET title='Tampered' WHERE id=1")
        self.assertEqual(sqlite3.connect(backup).execute("PRAGMA integrity_check").fetchone()[0], "ok")
        destination = self.root / "must-not-be-created.sqlite3"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            restore_research_db(backup, destination, expected_sha256=recorded)
        self.assertFalse(destination.exists())

    def test_malformed_digest_rejected_before_create(self):
        self._seed()
        backup = self.root / "snapshot.sqlite3"
        backup_research_db(self.source_path, backup)
        target = self.root / "uncreated.sqlite3"
        with self.assertRaises(ValueError):
            restore_research_db(backup, target, expected_sha256="bad")
        self.assertFalse(target.exists())

    def test_recovery_drill_uses_separate_receipt_and_compares_restored_archive(self):
        first, claim = self._seed()
        backup = self.root / "backups" / "snapshot.sqlite3"
        receipt = self.root / "receipts" / "snapshot.json"
        result = backup_with_receipt(self.source_path, backup, receipt)
        self.assertEqual(result["source_count"], 1)
        self.assertTrue(backup.is_file())
        self.assertTrue(receipt.is_file())
        self.assertNotEqual(backup.parent, receipt.parent)
        expected = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(expected["sha256"], result["sha256"])
        target = self.root / "recovered" / "rehearsal.sqlite3"
        verified = recovery_drill(backup, receipt, target)
        self.assertTrue(verified["verified"])
        self.assertEqual(verified["source_count"], 1)
        self.assertEqual(verified["claim_count"], 1)
        self.assertEqual(KnowledgeStore(target).list_source_manifest_links(),
                         self.store.list_source_manifest_links())
        self.assertEqual(KnowledgeStore(target).list_review_notes(claim["id"]),
                         self.store.list_review_notes(claim["id"]))

    def test_recovery_drill_rejects_tampered_valid_sqlite_before_destination(self):
        self._seed()
        backup = self.root / "backups" / "snapshot.sqlite3"
        receipt = self.root / "receipts" / "snapshot.json"
        backup_with_receipt(self.source_path, backup, receipt)
        import sqlite3
        with sqlite3.connect(backup) as conn:
            conn.execute("UPDATE sources SET title='Changed after backup'")
        self.assertEqual(sqlite3.connect(backup).execute("PRAGMA integrity_check").fetchone()[0], "ok")
        target = self.root / "recovered" / "should-not-exist.sqlite3"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            recovery_drill(backup, receipt, target)
        self.assertFalse(target.exists())

    def test_backup_with_receipt_rejects_preexisting_receipt_without_creating_backup(self):
        self._seed()
        backup = self.root / "backups" / "snapshot.sqlite3"
        receipt = self.root / "receipts" / "existing.json"
        receipt.parent.mkdir()
        receipt.write_text("unrelated", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            backup_with_receipt(self.source_path, backup, receipt)
        self.assertFalse(backup.exists())
        self.assertEqual(receipt.read_text(encoding="utf-8"), "unrelated")

    def test_receipt_write_failure_removes_only_new_backup_and_receipt(self):
        self._seed()
        before = self.store.list_sources()
        backup = self.root / "snapshots" / "new.sqlite3"
        receipt = self.root / "receipts" / "new.json"
        with patch("core.sqlite_backup.json.dump", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                backup_with_receipt(self.source_path, backup, receipt)
        self.assertFalse(backup.exists())
        self.assertFalse(receipt.exists())
        self.assertEqual(self.store.list_sources(), before)

    def test_unwritable_receipt_parent_leaves_no_orphan_backup(self):
        self._seed()
        marker = self.root / "not-a-directory"
        marker.write_text("untouched", encoding="utf-8")
        backup = self.root / "snapshots" / "new.sqlite3"
        receipt = marker / "new.json"
        with self.assertRaises(OSError):
            backup_with_receipt(self.source_path, backup, receipt)
        self.assertFalse(backup.exists())
        self.assertEqual(marker.read_text(encoding="utf-8"), "untouched")

    def test_receipt_count_mismatch_rejected_before_recovery_file_is_written(self):
        self._seed()
        backup = self.root / "separate" / "snapshot.sqlite3"
        receipt = self.root / "receipts" / "snapshot.json"
        backup_with_receipt(self.source_path, backup, receipt)
        data = json.loads(receipt.read_text(encoding="utf-8"))
        data["source_count"] += 1
        receipt.write_text(json.dumps(data), encoding="utf-8")
        target = self.root / "restored" / "no-output.sqlite3"
        with self.assertRaisesRegex(ValueError, "record counts"):
            recovery_drill(backup, receipt, target)
        self.assertFalse(target.exists())

    def test_recovery_drill_rejects_foreign_key_broken_backup_before_creating_target(self):
        self._seed()
        backup = self.root / "separate" / "snapshot.sqlite3"
        receipt = self.root / "receipts" / "snapshot.json"
        backup_with_receipt(self.source_path, backup, receipt)
        import sqlite3
        with sqlite3.connect(backup) as conn:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("INSERT INTO claim_sources(claim_id,source_id,relationship) VALUES(99999,99999,'supports')")
        import hashlib
        data = json.loads(receipt.read_text(encoding="utf-8"))
        data["sha256"] = hashlib.sha256(backup.read_bytes()).hexdigest()
        receipt.write_text(json.dumps(data), encoding="utf-8")
        target = self.root / "restored" / "should-not-exist.sqlite3"
        with self.assertRaisesRegex(ValueError, "foreign key"):
            recovery_drill(backup, receipt, target)
        self.assertFalse(target.exists())

    def test_backup_never_overwrites_existing_file(self):
        self._seed()
        backup_path = self.root / "existing.backup"
        backup_path.write_bytes(b"keep this")
        with self.assertRaises(FileExistsError):
            backup_research_db(self.source_path, backup_path)
        self.assertEqual(backup_path.read_bytes(), b"keep this")

    def test_restore_refuses_overwrite_of_existing_live_database(self):
        self._seed()
        backup_path = self.root / "snapshot.sqlite3"
        backup_research_db(self.source_path, backup_path)
        with self.assertRaises(FileExistsError):
            restore_research_db(backup_path, self.source_path)
        self.assertEqual(len(self.store.list_sources()), 1)

    def test_restore_rejects_invalid_backup_without_new_destination(self):
        garbage = self.root / "garbage.sqlite3"
        garbage.write_bytes(b"not a sqlite file")
        target = self.root / "restored.sqlite3"
        with self.assertRaises(ValueError):
            restore_research_db(garbage, target)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
