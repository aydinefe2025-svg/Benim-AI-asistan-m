import sys
import types
import unittest
from unittest.mock import patch

from core.groq_chat_client import GroqChatClient
from core.google_chat_client import GoogleChatClient


class ProviderRateLimitError(Exception):
    status_code = 429


class GoogleSdkRateLimitError(Exception):
    code = 429


class ProviderFailureMetadataTests(unittest.TestCase):
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
                GroqChatClient("test-key").chat("test-model", "system", "prompt")

        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.failure_kind, "rate_limit")
        self.assertNotIn("private provider response body", str(caught.exception))

    def test_allowlisted_groq_code_survives_safe_wrapping(self):
        error = Exception("private provider response body")
        error.status_code = 400
        error.body = {"error": {"code": "unsupported_parameter", "message": "PRIVATE"}}
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
                GroqChatClient("test-key").chat("test-model", "system", "prompt")
        self.assertEqual(caught.exception.failure_code, "unsupported_parameter")
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_google_sdk_code_survives_safe_adapter_wrapping(self):
        error = GoogleSdkRateLimitError("private provider response body")
        fake_genai = types.SimpleNamespace(
            Client=lambda **kwargs: types.SimpleNamespace(
                models=types.SimpleNamespace(
                    generate_content=lambda **kw: (_ for _ in ()).throw(error)
                ),
                close=lambda: None,
            )
        )
        fake_types = types.SimpleNamespace(
            HttpOptions=lambda **kwargs: kwargs,
            HttpRetryOptions=lambda **kwargs: kwargs,
            GenerateContentConfig=lambda **kwargs: kwargs,
        )
        fake_google = types.ModuleType("google")
        fake_google.__path__ = []
        fake_google.genai = fake_genai
        fake_google_genai = types.ModuleType("google.genai")
        fake_google_genai.Client = fake_genai.Client
        fake_google_types = types.ModuleType("google.genai.types")
        fake_google_types.HttpOptions = fake_types.HttpOptions
        fake_google_types.HttpRetryOptions = fake_types.HttpRetryOptions
        fake_google_types.GenerateContentConfig = fake_types.GenerateContentConfig

        with patch.dict(sys.modules, {
            "google": fake_google,
            "google.genai": fake_google_genai,
            "google.genai.types": fake_google_types,
        }):
            with self.assertRaises(RuntimeError) as caught:
                GoogleChatClient("test-key").chat("test-model", "system", "prompt")

        self.assertEqual(caught.exception.status_code, 429)
        self.assertEqual(caught.exception.failure_kind, "rate_limit")
        self.assertNotIn("private provider response body", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
