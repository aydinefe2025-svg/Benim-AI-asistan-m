import tempfile
import unittest
from pathlib import Path

from core.knowledge_store import KnowledgeStore, sha256_text


class KnowledgeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = KnowledgeStore(Path(self.tempdir.name) / "knowledge.sqlite3")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_source_content_hash(self):
        source = self.store.add_source(
            "https://example.org/paper", "Example paper", content="sample text"
        )
        self.assertEqual(source["content_sha256"], sha256_text("sample text"))

    def test_duplicate_url_updates_same_source(self):
        first = self.store.add_source("https://example.org/a", "Old title")
        second = self.store.add_source("https://example.org/a", "New title")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.store.list_sources()), 1)
        self.assertEqual(second["title"], "New title")

    def test_claim_requires_existing_source(self):
        with self.assertRaises(ValueError):
            self.store.add_claim("Uncited claim", [99])

    def test_claim_keeps_support_and_contradiction_links(self):
        a = self.store.add_source("https://example.org/a", "Source A")
        b = self.store.add_source("https://example.org/b", "Source B")
        claim = self.store.add_claim(
            "A testable claim", [a["id"], b["id"]], status="contested",
            confidence=0.4, relationships={a["id"]: "supports", b["id"]: "contradicts"}
        )
        loaded = self.store.get_claim(claim["id"])
        self.assertEqual(loaded["status"], "contested")
        self.assertEqual(
            {item["relationship"] for item in loaded["sources"]},
            {"supports", "contradicts"},
        )

    def test_sparse_reimport_preserves_metadata(self):
        original = self.store.add_source(
            "https://example.org/report", "Report", publisher="Museum",
            published_at="2026-10-01", notes="Original review",
            content="version one",
        )
        updated = self.store.add_source("https://example.org/report", "Report, new title")
        self.assertEqual(updated["id"], original["id"])
        self.assertEqual(updated["publisher"], "Museum")
        self.assertEqual(updated["published_at"], "2026-10-01")
        self.assertEqual(updated["notes"], "Original review")
        self.assertEqual(updated["content_sha256"], sha256_text("version one"))

    def test_new_metadata_can_replace_old_metadata(self):
        source = self.store.add_source("https://example.org/b", "Old", publisher="Old publisher")
        updated = self.store.add_source("https://example.org/b", "New", publisher="New publisher")
        self.assertEqual(source["id"], updated["id"])
        self.assertEqual(updated["publisher"], "New publisher")

    def test_content_digest_history_kept_and_idempotent(self):
        source = self.store.add_source("https://example.org/a", "A", content="first")
        self.store.add_source("https://example.org/a", "A", content="second")
        self.store.add_source("https://example.org/a", "A", content="second")
        self.store.add_source("https://example.org/a", "A")
        fingerprints = [row["content_sha256"] for row in self.store.list_revisions(source["id"])]
        self.assertEqual(fingerprints, [sha256_text("first"), sha256_text("second")])

    def test_unknown_source_revision_lookup_fails(self):
        with self.assertRaises(KeyError):
            self.store.list_revisions(987654)

    def test_migration_preserves_latest_existing_digest(self):
        source = self.store.add_source("https://example.org/a", "A", content="snapshot")
        # Simulate database produced by an earlier code version without the history table.
        with self.store._connect() as conn:
            conn.execute("DROP TABLE source_revisions")
        migrated = KnowledgeStore(self.store.db_path)
        fingerprints = [x["content_sha256"] for x in migrated.list_revisions(source["id"])]
        self.assertEqual(fingerprints, [sha256_text("snapshot")])

    def test_supported_rejected_for_url_only_source(self):
        source = self.store.add_source("https://example.org/unchecked", "Not independently checked")
        with self.assertRaisesRegex(ValueError, "review"):
            self.store.add_claim("Not yet proven", [source["id"]], status="supported", confidence=1.0)
        self.assertEqual(self.store.list_claims(), [])

    def test_supported_rejected_even_when_source_text_is_hashed(self):
        source = self.store.add_source("https://example.org/checked", "Article", content="Full text")
        self.assertTrue(source["content_sha256"])
        with self.assertRaisesRegex(ValueError, "review"):
            self.store.add_claim("Claim not independently reviewed", [source["id"]], status="supported")
        self.assertEqual(self.store.list_claims(), [])

    def test_supported_rejected_with_contradictory_source(self):
        one = self.store.add_source("https://example.org/a", "A", content="One interpretation")
        two = self.store.add_source("https://example.org/b", "B", content="Contrary interpretation")
        with self.assertRaisesRegex(ValueError, "review"):
            self.store.add_claim("Contested proposition", [one["id"], two["id"]],
                                 status="supported", relationships={two["id"]: "contradicts"})
        self.assertEqual(self.store.list_claims(), [])

    def test_unreviewed_claim_remains_usable(self):
        source = self.store.add_source("https://example.org/u", "Unreviewed")
        claim = self.store.add_claim("Pending claim", [source["id"]])
        self.assertEqual(claim["status"], "unreviewed")
        self.assertEqual(self.store.get_claim(claim["id"])["status"], "unreviewed")

    def test_legacy_supported_rows_remain_without_automatic_promotion(self):
        source = self.store.add_source("https://example.org/old", "Legacy source")
        with self.store._connect() as conn:
            conn.execute(
                "INSERT INTO claims(claim,status,confidence,created_at) VALUES(?,?,?,?)",
                ("Old supported status", "supported", 0.6, "2026-01-01T00:00:00+00:00"),
            )
            claim_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("INSERT INTO claim_sources(claim_id,source_id,relationship) VALUES(?,?,'supports')",
                         (claim_id, source["id"]))
        self.assertEqual(self.store.get_claim(claim_id)["status"], "supported")
        self.assertEqual(len(self.store.list_claims(status="supported")), 1)

    def test_rejects_non_http_url_and_bad_confidence(self):
        with self.assertRaises(ValueError):
            self.store.add_source("file:///etc/passwd", "Bad")
        source = self.store.add_source("https://example.org/good", "Good")
        with self.assertRaises(ValueError):
            self.store.add_claim("Bad confidence", [source["id"]], confidence=1.1)


if __name__ == "__main__":
    unittest.main()
