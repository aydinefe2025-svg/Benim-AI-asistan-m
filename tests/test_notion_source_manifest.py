"""Regression tests for conservative, deterministic Notion source ingestion."""
import tempfile
import unittest
from pathlib import Path

from core.knowledge_store import KnowledgeStore
from core.notion_source_manifest import import_source_manifest


class NotionSourceManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = KnowledgeStore(Path(self.tmp.name) / "knowledge.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_imports_valid_sources_with_stable_ids_and_no_claims(self):
        entries = [
            {"url": "https://doi.org/10.1234/alpha", "title": "Original paper",
             "publisher": "Test Journal", "notion_page_id": "page-001"},
            {"url": "https://doi.org/10.1234/alpha", "title": "Original paper",
             "notion_page_id": "page-001"},
            {"url": "https://doi.org/10.1234/beta", "title": "Independent source",
             "notion_page_id": "page-002"},
        ]
        first = import_source_manifest(self.store, entries)
        second = import_source_manifest(self.store, entries)
        self.assertEqual(first["imported"], 2)
        self.assertEqual(first["duplicates_skipped"], 1)
        self.assertEqual(second["imported"], 0)
        self.assertEqual(len(self.store.list_sources()), 2)
        self.assertEqual(self.store.list_sources()[0]["publisher"], "Test Journal")
        self.assertEqual(self.store.list_claims(), [])
        self.assertEqual(first["claim_count_created"], 0)

    def test_invalid_entry_rejects_whole_manifest_before_writing(self):
        good = {"url": "https://example.org/a", "title": "A", "notion_page_id": "page"}
        bad = {"url": "javascript:alert(1)", "title": "B", "notion_page_id": "page"}
        with self.assertRaises(ValueError):
            import_source_manifest(self.store, [good, bad])
        self.assertEqual(self.store.list_sources(), [])

    def test_requires_explicit_notional_provenance_and_does_not_assume_content(self):
        for entry in [
            {"url": "https://example.org/a", "title": "A"},
            {"url": "https://example.org/a", "title": "A", "notion_page_id": ""},
            {"url": "https://example.org/a", "title": "", "notion_page_id": "page"},
        ]:
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                import_source_manifest(self.store, [entry])
        result = import_source_manifest(self.store, [
            {"url": "https://example.org/a", "title": "A", "notion_page_id": "page"}
        ])
        self.assertEqual(result["imported"], 1)
        self.assertEqual(self.store.list_sources()[0]["content_sha256"], "")

    def test_same_url_conflicting_titles_in_single_batch_rejected(self):
        with self.assertRaises(ValueError):
            import_source_manifest(self.store, [
                {"url": "https://example.org/a", "title": "First", "notion_page_id": "a"},
                {"url": "https://example.org/a", "title": "Other", "notion_page_id": "a"},
            ])
        self.assertEqual(self.store.list_sources(), [])


if __name__ == "__main__":
    unittest.main()
