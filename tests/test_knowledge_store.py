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

    def test_review_note_records_claim_source_hash_at_review_time(self):
        source = self.store.add_source("https://example.org/study", "Study", content="v1")
        claim = self.store.add_claim("Review this", [source["id"]])
        event = self.store.add_review_note(
            claim["id"], source["id"], reviewer_label="editor-a",
            assessment="needs_more_evidence", rationale="Missing control sample",
        )
        self.assertEqual(event["source_sha256"], sha256_text("v1"))
        self.assertEqual(event["assessment"], "needs_more_evidence")
        self.assertEqual(event["reviewer_label"], "editor-a")
        self.store.add_source("https://example.org/study", "Study", content="v2")
        history = self.store.list_review_notes(claim["id"])
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["source_sha256"], sha256_text("v1"))
        self.assertEqual(self.store.get_claim(claim["id"])["status"], "unreviewed")

    def test_review_note_rejects_sources_not_linked_to_claim(self):
        one = self.store.add_source("https://example.org/one", "One")
        two = self.store.add_source("https://example.org/two", "Two")
        claim = self.store.add_claim("Linked only to one", [one["id"]])
        with self.assertRaises(ValueError):
            self.store.add_review_note(claim["id"], two["id"],
                reviewer_label="editor-b", assessment="disputed", rationale="No link")
        self.assertEqual(self.store.list_review_notes(claim["id"]), [])

    def test_review_note_validates_label_assessment_and_rationale(self):
        source = self.store.add_source("https://example.org/source", "Source")
        claim = self.store.add_claim("Claim", [source["id"]])
        for kwargs in [
            {"reviewer_label": "", "assessment": "disputed", "rationale": "reason"},
            {"reviewer_label": "bob", "assessment": "approved", "rationale": "reason"},
            {"reviewer_label": "bob", "assessment": "disputed", "rationale": ""},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.store.add_review_note(claim["id"], source["id"], **kwargs)
        self.assertEqual(self.store.list_review_notes(claim["id"]), [])

    def test_review_notes_do_not_authorize_supported_claim(self):
        source = self.store.add_source("https://example.org/credible", "Credible", content="article")
        claim = self.store.add_claim("Proposal", [source["id"]])
        self.store.add_review_note(claim["id"], source["id"],
            reviewer_label="untrusted-claimed-expert",
            assessment="supports", rationale="I think this supports it")
        with self.assertRaisesRegex(ValueError, "review"):
            self.store.add_claim("Unverified result", [source["id"]], status="supported")

    def test_audit_flags_source_without_fingerprint_and_missing_review(self):
        source = self.store.add_source("https://example.org/unread", "URL only")
        claim = self.store.add_claim("Pending", [source["id"]])
        audit = self.store.audit_claim_evidence(claim["id"])
        self.assertEqual(audit["claim_id"], claim["id"])
        self.assertEqual(audit["status"], "unreviewed")
        self.assertIn("source_without_content_hash", audit["flags"])
        self.assertIn("no_review_notes", audit["flags"])

    def test_audit_flags_review_based_on_obsolete_source_digest(self):
        source = self.store.add_source("https://example.org/data", "Data", content="v1")
        claim = self.store.add_claim("Old evaluation", [source["id"]])
        self.store.add_review_note(claim["id"], source["id"],
            reviewer_label="not-authenticated", assessment="supports", rationale="Preliminary")
        self.store.add_source("https://example.org/data", "Data", content="v2")
        audit = self.store.audit_claim_evidence(claim["id"])
        self.assertIn("review_source_digest_outdated", audit["flags"])
        self.assertIn("reviewer_identity_unverified", audit["flags"])

    def test_audit_flags_legacy_supported_and_contradictory_source(self):
        source = self.store.add_source("https://example.org/against", "Against", content="objection")
        claim = self.store.add_claim("Disputed", [source["id"]], status="contested",
            relationships={source["id"]: "contradicts"})
        with self.store._connect() as conn:
            conn.execute("UPDATE claims SET status='supported' WHERE id=?", (claim["id"],))
        audit = self.store.audit_claim_evidence(claim["id"])
        self.assertIn("legacy_supported_unverified", audit["flags"])
        self.assertIn("contradictory_source_link", audit["flags"])
        self.assertEqual(self.store.get_claim(claim["id"])["status"], "supported")

    def test_audit_retains_good_fingerprint_but_never_claims_independent_approval(self):
        source = self.store.add_source("https://example.org/stable", "Stable", content="unchanged")
        claim = self.store.add_claim("Hypothesis", [source["id"]])
        self.store.add_review_note(claim["id"], source["id"], reviewer_label="claimed-reviewer",
            assessment="needs_more_evidence", rationale="Need replication")
        flags = self.store.audit_claim_evidence(claim["id"])["flags"]
        self.assertNotIn("source_without_content_hash", flags)
        self.assertNotIn("review_source_digest_outdated", flags)
        self.assertNotIn("no_review_notes", flags)
        self.assertIn("reviewer_identity_unverified", flags)

    def test_rejects_non_http_url_and_bad_confidence(self):
        with self.assertRaises(ValueError):
            self.store.add_source("file:///etc/passwd", "Bad")
        source = self.store.add_source("https://example.org/good", "Good")
        with self.assertRaises(ValueError):
            self.store.add_claim("Bad confidence", [source["id"]], confidence=1.1)


if __name__ == "__main__":
    unittest.main()
