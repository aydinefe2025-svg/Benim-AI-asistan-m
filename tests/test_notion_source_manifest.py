"""Regression tests for conservative, deterministic Notion source ingestion."""
import json
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

    def test_real_notion_discovery_manifest_imports_28_distinct_sources(self):
        path = Path(__file__).resolve().parents[1] / "data" / "notion_discovery_sources_20261031.json"
        entries = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), 28)
        self.assertEqual([x["research_id"] for x in entries],
                         [f"D2026-{n:03d}" for n in range(1, 29)])
        self.assertEqual(len({x["url"] for x in entries}), 28)
        first = import_source_manifest(self.store, entries)
        second = import_source_manifest(self.store, entries)
        self.assertEqual(first["imported"], 28)
        self.assertEqual(second["imported"], 0)
        self.assertEqual(len(self.store.list_sources()), 28)
        self.assertEqual(self.store.list_claims(), [])
        self.assertTrue(all(not row["content_sha256"] for row in self.store.list_sources()))

    def test_database_failure_rolls_back_entire_manifest(self):
        with self.store._connect() as conn:
            conn.execute("""
                CREATE TRIGGER reject_second_source
                BEFORE INSERT ON sources
                WHEN NEW.url = 'https://example.org/boom'
                BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END
            """)
        entries = [
            {"url": "https://example.org/first", "title": "First",
             "notion_page_id": "notion-page-1"},
            {"url": "https://example.org/boom", "title": "Fails",
             "notion_page_id": "notion-page-2"},
        ]
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            import_source_manifest(self.store, entries)
        self.assertEqual(self.store.list_sources(), [])
        self.assertEqual(self.store.list_claims(), [])

    def test_database_failure_leaves_existing_source_unmodified(self):
        original = self.store.add_source(
            "https://example.org/existing", "Original",
            publisher="Publisher", notes="Original provenance", content="body",
        )
        with self.store._connect() as conn:
            conn.execute("""
                CREATE TRIGGER block_late_record
                BEFORE INSERT ON sources
                WHEN NEW.url = 'https://example.org/boom'
                BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END
            """)
        entries = [
            {"url": "https://example.org/existing", "title": "New title",
             "notion_page_id": "new-page"},
            {"url": "https://example.org/boom", "title": "Fails",
             "notion_page_id": "page"},
        ]
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            import_source_manifest(self.store, entries)
        current = self.store.list_sources()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["title"], original["title"])
        self.assertEqual(current[0]["notes"], original["notes"])
        self.assertEqual(current[0]["content_sha256"], original["content_sha256"])

    def test_expanded_real_notion_manifest_keeps_all_34_sources_and_first_28(self):
        folder = Path(__file__).resolve().parents[1] / "data"
        original = json.loads((folder / "notion_discovery_sources_20261031.json").read_text(encoding="utf-8"))
        updated = json.loads((folder / "notion_discovery_sources_20261031_v2.json").read_text(encoding="utf-8"))
        self.assertEqual(len(original), 28)
        self.assertEqual(len(updated), 34)
        self.assertEqual(updated[:28], original)
        self.assertEqual(
            [x["research_id"] for x in updated],
            [f"D2026-{i:03d}" for i in range(1, 35)],
        )
        self.assertEqual(len({x["url"] for x in updated}), 34)
        result = import_source_manifest(self.store, updated)
        self.assertEqual(result["imported"], 34)
        self.assertEqual(len(self.store.list_sources()), 34)
        self.assertEqual(import_source_manifest(self.store, updated)["imported"], 0)
        self.assertEqual(self.store.list_claims(), [])
        self.assertTrue(all(not x["content_sha256"] for x in self.store.list_sources()))

    def test_expanded_manifest_incremental_import_only_adds_six(self):
        folder = Path(__file__).resolve().parents[1] / "data"
        original = json.loads((folder / "notion_discovery_sources_20261031.json").read_text(encoding="utf-8"))
        updated = json.loads((folder / "notion_discovery_sources_20261031_v2.json").read_text(encoding="utf-8"))
        first = import_source_manifest(self.store, original)
        self.assertEqual(first["imported"], 28)
        second = import_source_manifest(self.store, updated)
        self.assertEqual(second["imported"], 6)
        self.assertEqual(second["processed_unique"], 34)
        self.assertEqual(len(self.store.list_sources()), 34)
        self.assertEqual(self.store.list_claims(), [])

    def test_v3_manifest_keeps_all_36_research_links_and_no_auto_approval(self):
        folder = Path(__file__).resolve().parents[1] / "data"
        v2 = json.loads((folder / "notion_discovery_sources_20261031_v2.json").read_text(encoding="utf-8"))
        v3 = json.loads((folder / "notion_discovery_sources_20261031_v3.json").read_text(encoding="utf-8"))
        self.assertEqual(len(v2), 34)
        self.assertEqual(len(v3), 36)
        self.assertEqual(v3[:34], v2)
        self.assertEqual([x["research_id"] for x in v3],
                         [f"D2026-{i:03d}" for i in range(1, 37)])
        self.assertEqual(len({x["url"] for x in v3}), 36)
        self.assertTrue(all(x["notion_page_id"] for x in v3))
        result = import_source_manifest(self.store, v3)
        self.assertEqual(result["imported"], 36)
        self.assertEqual(import_source_manifest(self.store, v3)["imported"], 0)
        self.assertEqual(len(self.store.list_sources()), 36)
        self.assertEqual(self.store.list_claims(), [])
        self.assertTrue(all(x["content_sha256"] == "" for x in self.store.list_sources()))

    def test_v2_to_v3_adds_only_two_without_overwriting_known_metadata(self):
        folder = Path(__file__).resolve().parents[1] / "data"
        v2 = json.loads((folder / "notion_discovery_sources_20261031_v2.json").read_text(encoding="utf-8"))
        v3 = json.loads((folder / "notion_discovery_sources_20261031_v3.json").read_text(encoding="utf-8"))
        self.assertEqual(import_source_manifest(self.store, v2)["imported"], 34)
        self.assertEqual(import_source_manifest(self.store, v3)["imported"], 2)
        self.assertEqual(len(self.store.list_sources()), 36)
        self.assertEqual(self.store.list_claims(), [])

    def test_research_id_links_preserved_in_database_and_resolvable(self):
        path = Path(__file__).resolve().parents[1] / "data" / "notion_discovery_sources_20261031_v3.json"
        v3 = json.loads(path.read_text(encoding="utf-8"))
        import_source_manifest(self.store, v3)
        links = self.store.list_source_manifest_links()
        self.assertEqual(len(links), 36)
        self.assertEqual([x["research_id"] for x in links],
                         [f"D2026-{i:03d}" for i in range(1, 37)])
        self.assertEqual(links[34]["url"], v3[34]["url"])
        self.assertEqual(links[35]["notion_page_id"], v3[35]["notion_page_id"])
        self.assertEqual(len({x["source_id"] for x in links}), 36)
        self.assertEqual(import_source_manifest(self.store, v3)["imported"], 0)
        self.assertEqual(self.store.list_source_manifest_links(), links)

    def test_research_id_reassigned_to_another_url_is_rejected_and_rolled_back(self):
        a = [{"research_id": "D2026-001", "url": "https://example.org/a",
              "title": "A", "notion_page_id": "page"}]
        import_source_manifest(self.store, a)
        with self.assertRaises(ValueError):
            import_source_manifest(self.store, [
                {"research_id": "D2026-002", "url": "https://example.org/new",
                 "title": "New", "notion_page_id": "page"},
                {"research_id": "D2026-001", "url": "https://example.org/b",
                 "title": "Conflict", "notion_page_id": "page"},
            ])
        self.assertEqual([x["url"] for x in self.store.list_sources()], ["https://example.org/a"])
        self.assertEqual(len(self.store.list_source_manifest_links()), 1)

    def test_research_id_collision_within_batch_is_rejected_before_writes(self):
        with self.assertRaises(ValueError):
            import_source_manifest(self.store, [
                {"research_id": "D2026-001", "url": "https://example.org/a",
                 "title": "A", "notion_page_id": "page"},
                {"research_id": "D2026-001", "url": "https://example.org/b",
                 "title": "B", "notion_page_id": "page"},
            ])
        self.assertEqual(self.store.list_sources(), [])

    def test_same_research_id_cannot_silently_move_to_different_notion_page(self):
        original = [{"research_id": "D2026-001", "url": "https://example.org/source",
                     "title": "Source", "notion_page_id": "original-page"}]
        import_source_manifest(self.store, original)
        before = self.store.list_source_manifest_links()
        with self.assertRaisesRegex(ValueError, "Notion page"):
            import_source_manifest(self.store, [
                {"research_id": "D2026-002", "url": "https://example.org/temporary",
                 "title": "Temporary", "notion_page_id": "another-page"},
                {"research_id": "D2026-001", "url": "https://example.org/source",
                 "title": "Changed title", "notion_page_id": "different-page"},
            ])
        self.assertEqual(self.store.list_source_manifest_links(), before)
        self.assertEqual(len(self.store.list_sources()), 1)
        self.assertEqual(self.store.list_sources()[0]["title"], "Source")

    def test_same_source_url_can_support_two_research_records(self):
        items = [
            {"research_id": "D2026-001", "url": "https://example.org/shared",
             "title": "Shared paper", "notion_page_id": "page-a"},
            {"research_id": "D2026-002", "url": "https://example.org/shared",
             "title": "Shared paper", "notion_page_id": "page-b"},
        ]
        result = import_source_manifest(self.store, items)
        self.assertEqual(result["imported"], 1)
        self.assertEqual(len(self.store.list_sources()), 1)
        links = self.store.list_source_manifest_links()
        self.assertEqual(len(links), 2)
        self.assertEqual({x["notion_page_id"] for x in links}, {"page-a", "page-b"})
        self.assertEqual(links[0]["source_id"], links[1]["source_id"])
        import_source_manifest(self.store, items)
        self.assertEqual(self.store.list_source_manifest_links(), links)

    def test_same_url_conflicting_titles_in_single_batch_rejected(self):
        with self.assertRaises(ValueError):
            import_source_manifest(self.store, [
                {"url": "https://example.org/a", "title": "First", "notion_page_id": "a"},
                {"url": "https://example.org/a", "title": "Other", "notion_page_id": "a"},
            ])
        self.assertEqual(self.store.list_sources(), [])


if __name__ == "__main__":
    unittest.main()
