"""Regression: never queue or echo hyphenated API credential shapes.

Only a synthetic dummy key is used. No real secrets or network calls.
"""
import unittest

from core.cano_code_jobs import parse_code_request
from core.cano_solution_dispatch import actionable_solution, infer_code_goal


class HyphenatedSecretGateTests(unittest.TestCase):
    def setUp(self):
        # Deliberately nonfunctional, synthetic shape, not a credential.
        self.fake_key = "sk-" + "proj-" + "Q" * 24

    def test_explicit_owner_code_request_rejects_hyphenated_key(self):
        with self.assertRaises(ValueError):
            parse_code_request("CANO kod: Uygulama testini düzelt " + self.fake_key)

    def test_natural_owner_code_goal_rejects_hyphenated_key(self):
        request = "CANO web kodunu düzelt " + self.fake_key
        self.assertIsNone(infer_code_goal(request, []))

    def test_followup_never_copies_hyphenated_key_from_assistant(self):
        previous = "CANO uygulamasını düzelt ve test et. " + self.fake_key
        self.assertFalse(actionable_solution(previous))
        self.assertIsNone(infer_code_goal(
            "CANO bunu uygula", [{"role": "assistant", "content": previous}]
        ))


if __name__ == "__main__":
    unittest.main()
