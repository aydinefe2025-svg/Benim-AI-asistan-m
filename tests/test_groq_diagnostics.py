"""Groq health checks must stay read-only and return no provider error text."""
from types import SimpleNamespace
import unittest

from core.groq_diagnostics import check_groq_connection


class GroqDiagnosticsTests(unittest.TestCase):
    def test_reports_model_presence_from_models_list(self):
        calls = []

        class Models:
            def list(self):
                calls.append("list")
                return SimpleNamespace(data=[SimpleNamespace(id="openai/gpt-oss-120b")])

        class FakeClient:
            models = Models()

        result = check_groq_connection(
            "dummy-test-value",
            "openai/gpt-oss-120b",
            client_factory=lambda **kwargs: FakeClient(),
        )
        self.assertEqual(calls, ["list"])
        self.assertEqual(result, {"reachable": True, "model_available": True})

    def test_missing_model_does_not_claim_model_access(self):
        class Models:
            def list(self):
                return SimpleNamespace(data=[SimpleNamespace(id="different-model")])

        class FakeClient:
            models = Models()

        self.assertEqual(
            check_groq_connection("dummy-test-value", "openai/gpt-oss-120b",
                                  client_factory=lambda **kwargs: FakeClient()),
            {"reachable": True, "model_available": False},
        )

    def test_provider_error_is_suppressed(self):
        sensitive_message = "never include provider exception text"

        class FakeClient:
            class models:
                @staticmethod
                def list():
                    raise RuntimeError(sensitive_message)

        result = check_groq_connection(
            "dummy-test-value",
            "openai/gpt-oss-120b",
            client_factory=lambda **kwargs: FakeClient(),
        )
        self.assertEqual(result, {"reachable": False, "model_available": False})
        self.assertNotIn(sensitive_message, repr(result))


if __name__ == "__main__":
    unittest.main()
