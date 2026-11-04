import unittest
from unittest.mock import patch

from core.web_search import DuckDuckGoSearch, SearchError


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class WebSearchTests(unittest.TestCase):
    def test_parses_result_title_url_snippet(self):
        html = b"""
        <div class="result results_links">
          <div class="result__body">
            <h2><a class="result__a" href="https://example.org/paper">Example Paper</a></h2>
            <a class="result__snippet">A <b>useful</b> search snippet.</a>
          </div>
        </div>
        """
        with patch("core.web_search.urlopen", return_value=FakeResponse(html)):
            results = DuckDuckGoSearch().search("test topic")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Example Paper")
        self.assertEqual(results[0].url, "https://example.org/paper")
        self.assertEqual(results[0].snippet, "A useful search snippet.")
        self.assertEqual(results[0].publisher, "example.org")

    def test_empty_query_rejected(self):
        with self.assertRaises(ValueError):
            DuckDuckGoSearch().search("  ")

    def test_no_results_is_not_silently_claimed_as_success(self):
        with patch("core.web_search.urlopen", return_value=FakeResponse(b"<html>blocked</html>")):
            with self.assertRaises(SearchError):
                DuckDuckGoSearch().search("some query")


if __name__ == "__main__":
    unittest.main()
