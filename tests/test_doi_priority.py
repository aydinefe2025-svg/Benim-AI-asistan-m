import unittest

from core.doi_priority import prioritize_requested_dois, requested_doi_leads


class RequestedDoiTests(unittest.TestCase):
    def test_extracts_multiple_requested_dois_in_order_and_deduplicates(self):
        task = "Paper DOI 10.1136/bmj-2023-075847; correction 10.1136/bmj.q1024."
        self.assertEqual(
            [lead["url"] for lead in requested_doi_leads(task)],
            ["https://doi.org/10.1136/bmj-2023-075847",
             "https://doi.org/10.1136/bmj.q1024"],
        )

    def test_explicit_dois_precede_and_deduplicate_crossref_candidates(self):
        task = "See 10.1136/bmj-2023-075847 and 10.1136/bmj.q1024"
        candidates = [
            {"title": "Wrong relevance match", "url": "https://doi.org/10.64239/pi-tr-qt4802"},
            {"title": "Correction", "url": "https://doi.org/10.1136/bmj.q1024"},
        ]
        leads = prioritize_requested_dois(task, candidates, limit=3)
        self.assertEqual(
            [lead["url"] for lead in leads],
            ["https://doi.org/10.1136/bmj-2023-075847",
             "https://doi.org/10.1136/bmj.q1024",
             "https://doi.org/10.64239/pi-tr-qt4802"],
        )

    def test_limits_and_rejects_invalid_control_values(self):
        self.assertEqual(requested_doi_leads("DOI 10.1136/bmj.q1024", limit=0), [])
        self.assertEqual(requested_doi_leads("no DOI"), [])


if __name__ == "__main__":
    unittest.main()
