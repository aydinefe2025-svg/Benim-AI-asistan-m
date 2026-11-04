import unittest
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


if __name__ == "__main__":
    unittest.main()
