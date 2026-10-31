"""Backup/restore tests against real SQLite files and research lineage."""
import json
import tempfile
import unittest
from pathlib import Path

from core.knowledge_store import KnowledgeStore
from core.notion_source_manifest import import_source_manifest
from core.sqlite_backup import backup_research_db, restore_research_db


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
