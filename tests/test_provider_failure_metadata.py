import sys
import types
import unittest
from unittest.mock import patch

from core.groq_chat_client import GroqChatClient


class ProviderRateLimitError(Exception):
    status_code = 429


class GroqFailureMetadataTests(unittest.TestCase):
    def test_rate_limit_status_survives_safe_groq_wrapping(self):
        error = ProviderRateLimitError("private provider response body")
        completion = types.SimpleNamespace(create=lambda **kwargs: (_ for _ in ()).throw(error))
        fake_groq = types.SimpleNamespace(
            Groq=lambda **kwargs: types.SimpleNamespace(
                chat=types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=completion.create)
                )
            )
        )

        with patch.dict(sys.modules, {"groq": fake_groq}):
            with self.assertRaises(RuntimeError) as caught:
                GroqChatClient("test-key").chat(
                    "test-model", "system", "prompt")

        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.failure_kind, "rate_limit")
        self.assertNotIn("private provider response body", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
