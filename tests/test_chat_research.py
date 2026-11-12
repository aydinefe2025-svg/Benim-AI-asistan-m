import unittest

from core.chat_research import collect_chat_research_context, format_scholarly_leads


class ChatResearchTests(unittest.TestCase):
    def test_both_source_types_are_kept_separate_and_unverified(self):
        public = [{"title": "Wikipedia topic", "url": "https://en.wikipedia.org/wiki/Topic"}]
        scholarly = [{
            "title": "Candidate paper", "doi": "10.1234/example",
            "url": "https://doi.org/10.1234/example",
            "publisher": "Publisher", "published_at": "2025",
            "verified": False,
        }]
        calls = []
        result = collect_chat_research_context(
            "topic",
            public_lookup=lambda query: public,
            scholarly_lookup=lambda query, limit: scholarly,
            retrieve_excerpts=lambda sources: calls.append(sources) or [{"id": "W1", "text": "excerpt"}],
            format_evidence=lambda excerpts: "Wikipedia passage [W1]",
        )
        self.assertEqual(calls, [public])
        self.assertIn("Wikipedia passage [W1]", result["context"])
        self.assertIn("Crossref bibliography leads only", result["context"])
        self.assertIn("article text", result["context"])
        self.assertEqual(result["excerpts"][0]["id"], "W1")
        bibliography = format_scholarly_leads(result["scholarly_sources"])
        self.assertIn("https://doi.org/10.1234/example", bibliography)
        self.assertIn("doğrulanmış kanıt değildir", bibliography)

    def test_provider_failure_is_isolated_and_exception_message_is_not_exposed(self):
        def fail(_query):
            raise RuntimeError("secret request URL and token")
        result = collect_chat_research_context(
            "topic",
            public_lookup=fail,
            scholarly_lookup=lambda query, limit: [{
                "title": "Candidate", "doi": "10.1234/example",
            }],
            retrieve_excerpts=lambda _: [],
            format_evidence=lambda _: "No excerpts",
        )
        self.assertIn("Crossref bibliography leads only", result["context"])
        self.assertIn("RuntimeError", result["context"])
        self.assertNotIn("secret", result["context"])
        self.assertEqual(result["provider_errors"], ["RuntimeError"])

    def test_invalid_doi_does_not_become_a_citation(self):
        self.assertEqual(format_scholarly_leads([
            {"title": "Fake", "doi": "https://evil.invalid/path"},
        ]), "")


if __name__ == "__main__":
    unittest.main()
