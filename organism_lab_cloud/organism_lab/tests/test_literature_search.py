import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from organism_lab.literature_search import list_records, save_records, search_openalex


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.body[:size]


class LiteratureSearchTests(unittest.TestCase):
    def test_search_is_bounded_and_normalizes_catalog_metadata(self):
        document = {"results": [{
            "id": "https://openalex.org/W123",
            "title": "Digital evolution in Avida",
            "publication_year": 2023,
            "authorships": [{"author": {"display_name": "A. Researcher"}}],
            "doi": "https://doi.org/10.1234/example",
            "type": "article", "is_retracted": False,
            "primary_location": {"landing_page_url": "https://example.org/paper", "source": {"display_name": "Journal", "type": "journal"}},
            "open_access": {"oa_url": "https://example.org/open"},
        }]}
        seen = {}

        def opener(request, timeout):
            seen["url"] = request.full_url
            seen["timeout"] = timeout
            return FakeResponse(json.dumps(document).encode())

        result = search_openalex("digital evolution Avida", per_page=1, opener=opener)
        self.assertEqual(seen["timeout"], 12)
        self.assertIn("api.openalex.org/works?", seen["url"])
        self.assertIn("filter=type%3Aarticle%2Cis_retracted%3Afalse", seen["url"])
        self.assertEqual(result[0]["title"], "Digital evolution in Avida")
        self.assertEqual(result[0]["record_status"], "catalog_metadata_unverified")

    def test_rejects_invalid_query_and_large_result_count_before_network(self):
        with patch("organism_lab.literature_search.urlopen") as opener:
            for query, per_page in (("", 1), ("x" * 201, 1), ("valid", 11)):
                with self.assertRaises(ValueError):
                    search_openalex(query, per_page=per_page)
            opener.assert_not_called()

    def test_sqlite_upsert_is_deduplicated_and_unverified(self):
        record = {
            "openalex_id": "https://openalex.org/W123", "title": "Digital evolution",
            "publication_year": 2023, "authors": ["A. Researcher"], "doi": None,
            "landing_page_url": "https://example.org", "open_access_url": None,
            "venue": "Journal", "work_type": "article", "is_retracted": False, "source_type": "journal",
            "retrieved_at": "2026-11-02T00:00:00+00:00",
            "record_status": "catalog_metadata_unverified",
        }
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(save_records(temporary, "digital evolution", [record]), 1)
            self.assertEqual(save_records(temporary, "digital evolution", [record]), 1)
            rows = list_records(temporary)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["record_status"], "catalog_metadata_unverified")
            self.assertEqual(rows[0]["authors"], ["A. Researcher"])

    def test_rejects_non_article_and_retracted_records(self):
        from organism_lab.literature_search import _normalize_work
        base = {"id": "https://openalex.org/W123", "title": "Example", "type": "article", "is_retracted": False}
        self.assertIsNone(_normalize_work({**base, "type": "other"}, "now"))
        self.assertIsNone(_normalize_work({**base, "is_retracted": True}, "now"))
        self.assertIsNone(_normalize_work({**base, "primary_location": {"source": {"type": "repository"}}}, "now"))

    def test_migrates_existing_table_without_dropping_records(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "research_studies.sqlite3"
            connection = sqlite3.connect(database)
            try:
                connection.execute("""CREATE TABLE literature_records (
                    openalex_id TEXT PRIMARY KEY, query TEXT NOT NULL, title TEXT NOT NULL,
                    publication_year INTEGER, authors_json TEXT NOT NULL, doi TEXT,
                    landing_page_url TEXT, open_access_url TEXT, venue TEXT,
                    retrieved_at TEXT NOT NULL, record_status TEXT NOT NULL)""")
                connection.execute("INSERT INTO literature_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                   ("https://openalex.org/Wold", "old query", "Existing", 2020,
                                    "[]", None, None, None, None, "2026-01-01T00:00:00+00:00",
                                    "catalog_metadata_unverified"))
                connection.commit()
            finally:
                connection.close()
            record = {
                "openalex_id": "https://openalex.org/Wnew", "title": "New",
                "publication_year": 2024, "authors": [], "doi": None,
                "landing_page_url": None, "open_access_url": None, "venue": None,
                "work_type": "article", "is_retracted": False, "source_type": "journal",
                "retrieved_at": "2026-11-02T00:00:00+00:00",
                "record_status": "catalog_metadata_unverified",
            }
            save_records(temporary, "new query", [record])
            rows = list_records(temporary)
            self.assertEqual({row["openalex_id"] for row in rows},
                             {"https://openalex.org/Wold", "https://openalex.org/Wnew"})
            self.assertTrue(any(row["title"] == "Existing" and row["work_type"] is None for row in rows))

    def test_cannot_mark_records_as_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                save_records(temporary, "topic", [{"record_status": "verified"}])


if __name__ == "__main__":
    unittest.main()
