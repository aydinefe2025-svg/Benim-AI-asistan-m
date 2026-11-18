"""Synthetic SDK regression: blank successful replies must be response failures."""
import sys
import types
import unittest
from unittest.mock import patch

from core.google_chat_client import GoogleChatClient
from core.groq_chat_client import GroqChatClient
from core.provider_failure import failure_category, safe_failure_message


class EmptyProviderResponseTests(unittest.TestCase):
    def assert_response_error(self, action):
        with self.assertRaises(RuntimeError) as caught:
            action()
        error = caught.exception
        self.assertEqual(failure_category(error), "response")
        self.assertIn("boş", safe_failure_message(error))
        self.assertNotIn("SECRET", str(error))

    def test_groq_blank_completion_is_not_unknown(self):
        sdk = types.ModuleType("groq")
        class FakeGroq:
            def __init__(self, **_kwargs):
                self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(
                    create=lambda **_kwargs: types.SimpleNamespace(
                        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=" "))])
                ))
        sdk.Groq = FakeGroq
        with patch.dict(sys.modules, {"groq": sdk}):
            self.assert_response_error(
                lambda: GroqChatClient("synthetic-key").chat(
                    "openai/gpt-oss-120b", "system", "Hello"
                )
            )

    def test_google_blank_completion_is_not_unknown(self):
        google_package = types.ModuleType("google")
        google_package.__path__ = []
        genai = types.ModuleType("google.genai")
        fake_types = types.SimpleNamespace(
            HttpOptions=lambda **kw: kw,
            HttpRetryOptions=lambda **kw: kw,
            GenerateContentConfig=lambda **kw: kw,
        )
        class FakeGoogle:
            def __init__(self, **_kwargs):
                self.models = types.SimpleNamespace(
                    generate_content=lambda **_kwargs: types.SimpleNamespace(text=" ")
                )
            def close(self):
                pass
        genai.Client = FakeGoogle
        genai.types = fake_types
        google_package.genai = genai
        with patch.dict(sys.modules, {"google": google_package, "google.genai": genai}):
            self.assert_response_error(
                lambda: GoogleChatClient("synthetic-key").chat(
                    "gemini-3.6-flash", "system", "Hello"
                )
            )


if __name__ == "__main__":
    unittest.main()
