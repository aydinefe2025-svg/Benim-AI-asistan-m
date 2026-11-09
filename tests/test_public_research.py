import unittest
from urllib.parse import parse_qs, urlsplit
from core.public_research import research_sources


class ResearchTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(research_sources("  ", fetch=lambda url: {}), [])

    def test_sources(self):
        def mock(url):
            assert "gsrsearch=stellar+evolution" in url
            return {"query": {"pages": {
                "1": {"title": "Star", "fullurl": "https://en.wikipedia.org/wiki/Star"},
                "2": {"title": "Bad", "fullurl": "http://evil.invalid/"}
            }}}
        self.assertEqual(research_sources("stellar evolution", fetch=mock),
                         [{"title": "Star", "url": "https://en.wikipedia.org/wiki/Star"}])

    def test_limit(self):
        def mock(url):
            assert "gsrlimit=5" in url
            return {}
        self.assertEqual(research_sources("x", limit=999, fetch=mock), [])


    def test_turkish_research_instructions_reduce_to_topic(self):
        def mock(url):
            query = parse_qs(urlsplit(url).query)
            self.assertEqual(query["gsrsearch"], ["kütleçekimsel merceklenme"])
            return {"query": {"pages": {
                "1": {"title": "Kütleçekimsel merceklenme",
                      "fullurl": "https://tr.wikipedia.org/wiki/K%C3%BCtle%C3%A7ekimsel_merceklenme"}
            }}}
        results = research_sources(
            "Araştır kütleçekimsel merceklenme; kaynaklarını numaralı bağlantı olarak listele.",
            fetch=mock,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Kütleçekimsel merceklenme")

    def test_turkish_evidence_request_keeps_only_subject_terms(self):
        def mock(url):
            query = parse_qs(urlsplit(url).query)
            self.assertEqual(query["gsrsearch"], ["kütleçekimsel merceklenme"])
            return {}
        research_sources(
            "Araştır kütleçekimsel merceklenme. Yalnızca doğrulanmış kaynak pasajlarından "
            "numaralı bağlantı ver; pasaj alınamazsa bunu açıkça belirt.",
            fetch=mock,
        )

if __name__ == "__main__":
    unittest.main()
