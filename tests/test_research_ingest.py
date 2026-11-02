import tempfile
import unittest
from pathlib import Path

from core.knowledge_store import KnowledgeStore
from research_ingest import ingest_records


class ResearchIngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "research.sqlite3"
        self.records = [{
            "source_url": "https://example.org/research/one",
            "title": "Source One",
            "claim": "Source One is queued for evidence review.",
        }]

    def test_import_creates_unreviewed_context_record(self):
        result = ingest_records(self.records, self.db)
        self.assertEqual(result["new_unreviewed_claims"], 1)
        store = KnowledgeStore(self.db)
        claim = store.get_claim(store.list_claims()[0]["id"])
        self.assertEqual(claim["status"], "unreviewed")
        self.assertEqual(claim["sources"][0]["relationship"], "context")

    def test_repeated_import_does_not_duplicate_claim(self):
        ingest_records(self.records, self.db)
        result = ingest_records(self.records, self.db)
        self.assertEqual(result["new_unreviewed_claims"], 0)
        self.assertEqual(len(KnowledgeStore(self.db).list_claims()), 1)

    def test_invalid_batch_rejected_before_database_creation(self):
        with self.assertRaises(ValueError):
            ingest_records(self.records + [{"title": "missing"}], self.db)
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
