"""Exercise the actual app search helper without initializing Streamlit UI."""
import ast
import re
import types
import unittest
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urlencode
from unittest.mock import Mock


APP = Path(__file__).resolve().parents[1] / "app.py"


def load_search_function():
    """Compile the real app helper with isolated request/regex dependencies."""
    source = ast.parse(APP.read_text(encoding="utf-8"))
    helper = next(n for n in source.body
                  if isinstance(n, ast.FunctionDef) and n.name == "internette_ara")
    mocked_requests = types.SimpleNamespace(get=Mock())
    namespace = {"re": re, "requests": mocked_requests, "urlencode": urlencode}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(APP), "exec"), namespace)
    return namespace["internette_ara"], mocked_requests


class SearchProviderTests(unittest.TestCase):
    def test_weather_uses_valid_location_path(self):
        search, requests = load_search_function()
        requests.get.return_value = types.SimpleNamespace(
            status_code=200, text="Sunny +20C 40% 5km/h")
        answer = search("İzmir hava durumu")
        url = requests.get.call_args.args[0]
        self.assertEqual(urlsplit(url).netloc, "wttr.in")
        self.assertEqual(urlsplit(url).path, "/Izmir")
        self.assertIn("format", parse_qs(urlsplit(url).query))
        self.assertIn("İzmir", answer)

    def test_general_lookup_uses_instant_answer_endpoint_and_encoded_query(self):
        search, requests = load_search_function()
        requests.get.return_value = types.SimpleNamespace(
            status_code=200, json=lambda: {"AbstractText": "Ada Lovelace summary"})
        self.assertIn("Ada Lovelace summary", search("Ada Lovelace matematik"))
        url = requests.get.call_args.args[0]
        parts = urlsplit(url)
        self.assertEqual(parts.scheme, "https")
        self.assertEqual(parts.netloc, "api.duckduckgo.com")
        self.assertEqual(parts.path, "/")
        self.assertEqual(parse_qs(parts.query)["q"], ["Ada Lovelace matematik"])
        self.assertEqual(parse_qs(parts.query)["format"], ["json"])

    def test_empty_instant_answer_does_not_claim_full_web_search(self):
        search, requests = load_search_function()
        requests.get.return_value = types.SimpleNamespace(
            status_code=200, json=lambda: {"AbstractText": ""})
        answer = search("some obscure topic unknown to instant answers")
        self.assertIn("bulunamad", answer.lower())


if __name__ == "__main__":
    unittest.main()
