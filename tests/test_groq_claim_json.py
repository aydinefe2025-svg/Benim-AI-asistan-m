"""Strict JSON claim-review provider contract: no fabricated citation approval."""
import json
import unittest
from types import SimpleNamespace

from core.groq_claim_json import (
    generate_claim_quote_json, generate_claim_verification_json,
)
from core.groq_team import TeamRateLimitError


class Client:
    def __init__(self, response=None, failure=None, finish_reason="stop"):
        self.calls = []
        self.response = response or '{"claims":[]}'
        self.failure = failure
        self.finish_reason = finish_reason
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure
        return SimpleNamespace(choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=self.response),
                finish_reason=self.finish_reason,
            )
        ])


class GroqClaimJsonTests(unittest.TestCase):
    def test_skeptical_review_uses_strict_verdict_schema(self):
        fixture = {"assessments": [{
            "index": 0, "verdict": "insufficient", "reason": "Scope is missing."
        }]}
        client = Client(json.dumps(fixture))
        value = generate_claim_verification_json(
            "Skeptically review", "Untrusted claim and excerpt",
            api_key="dummy-key", client_factory=lambda **kw: client)
        self.assertEqual(json.loads(value), fixture)
        schema = client.calls[0]["response_format"]["json_schema"]["schema"]
        self.assertEqual(
            schema["properties"]["assessments"]["items"]["properties"]["verdict"]["enum"],
            ["supported", "contradicted", "insufficient"])
    def test_strict_schema_single_json_call_and_no_auto_claim_approval(self):
        fixture = {"claims": [
            {"claim": "A cautious proposal", "doi": "10.1234/test",
             "quote": "Verbatim excerpt from this hypothetical publication."}
        ]}
        client = Client(json.dumps(fixture))
        value = generate_claim_quote_json(
            "Validate excerpts, return JSON", "Untrusted source data",
            api_key="dummy-key", client_factory=lambda **kw: client)
        self.assertEqual(json.loads(value), fixture)
        self.assertEqual(len(client.calls), 1)
        params = client.calls[0]
        self.assertEqual(params["model"], "openai/gpt-oss-120b")
        self.assertEqual(params["response_format"]["type"], "json_schema")
        self.assertTrue(params["response_format"]["json_schema"]["strict"])
        schema = params["response_format"]["json_schema"]["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["properties"]["claims"]["items"]["additionalProperties"])
        self.assertEqual(params["reasoning_format"], "hidden")
        self.assertLessEqual(params["max_completion_tokens"], 1200)
        self.assertNotIn("verified", value)

    def test_zero_retries_and_no_secrets_exposed_on_rate_limit(self):
        class RateLimit(Exception):
            status_code = 429
        client = Client(failure=RateLimit("secret-password-do-not-log"))
        with self.assertRaises(TeamRateLimitError) as err:
            generate_claim_quote_json("JSON", "Proposal", api_key="dummy",
                                      client_factory=lambda **kw: client)
        self.assertEqual(len(client.calls), 1)
        self.assertNotIn("secret-password", str(err.exception))

    def test_other_provider_error_does_not_echo_credentials(self):
        client = Client(failure=RuntimeError("api_key=some-secret"))
        with self.assertRaises(RuntimeError) as err:
            generate_claim_quote_json("JSON", "Proposal", api_key="dummy",
                                      client_factory=lambda **kw: client)
        self.assertNotIn("some-secret", str(err.exception))

    def test_truncated_response_is_rejected(self):
        client = Client(finish_reason="length")
        with self.assertRaisesRegex(RuntimeError, "truncated"):
            generate_claim_quote_json("JSON", "Proposal", api_key="dummy",
                                      client_factory=lambda **kw: client)

    def test_malformed_json_and_invalid_shape_rejected(self):
        for value in ("prose with no JSON", '{"claims":42}', "[]"):
            client = Client(response=value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                generate_claim_quote_json("JSON", "Proposal", api_key="dummy",
                                          client_factory=lambda **kw: client)

    def test_no_provider_call_when_key_or_input_invalid(self):
        client = Client()
        for system, prompt, key in (("", "Task", "key"),
                                    ("JSON", "", "key"),
                                    ("JSON", "Task", ""),
                                    ("JSON", "x" * 10000, "key")):
            with self.subTest(key=bool(key)), self.assertRaises(ValueError):
                generate_claim_quote_json(system, prompt, api_key=key,
                                          client_factory=lambda **kw: client)
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
