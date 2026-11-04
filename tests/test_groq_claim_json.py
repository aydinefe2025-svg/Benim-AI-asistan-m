import unittest

from core.groq_claim_json import generate_claim_json
from core.groq_team import TeamRateLimitError


class StubResult:
    class Entry:
        class Msg:
            content = '{"claims":[]}'
        message = Msg()
    choices = [Entry()]


class StubClient:
    def __init__(self):
        self.calls = []
        self.chat = type("Chat", (), {})()
        self.chat.completions = type("Completion", (), {})()
        self.chat.completions.create = self.create

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return StubResult()


class EvidenceJsonTests(unittest.TestCase):
    def test_uses_json_object_mode_and_one_bounded_call(self):
        api = StubClient()
        response = generate_claim_json(
            "Return JSON only", "Review this retrieved quote.",
            api_key="test", client_factory=lambda **k: api)
        self.assertEqual(response, '{"claims":[]}')
        self.assertEqual(len(api.calls), 1)
        call = api.calls[0]
        self.assertEqual(call["response_format"], {"type":"json_object"})
        self.assertLessEqual(call["max_tokens"], 700)
        self.assertEqual(call["messages"][1]["content"],
                         "Review this retrieved quote.")

    def test_rate_limit_fails_closed_without_leaking_secret(self):
        api = StubClient()
        class Quota(Exception):
            status_code = 429
        def reject(**kwargs):
            raise Quota("private-org-and-api-key")
        api.chat.completions.create = reject
        with self.assertRaises(TeamRateLimitError) as error:
            generate_claim_json("Return JSON", "Review",
                                api_key="private-key", client_factory=lambda **k:api)
        self.assertNotIn("private", str(error.exception))

    def test_rejects_bad_input_before_network(self):
        api = StubClient()
        with self.assertRaises(ValueError):
            generate_claim_json(" ", "Quote", api_key="key",
                                client_factory=lambda **k:api)
        with self.assertRaises(ValueError):
            generate_claim_json("Return JSON", "x"*10000, api_key="key",
                                client_factory=lambda **k:api)
        self.assertEqual(api.calls, [])


if __name__ == "__main__":
    unittest.main()
