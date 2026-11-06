"""Credentials must be checked independently and never printed."""
import unittest
from core.provider_config import available_providers


class ProviderConfigTests(unittest.TestCase):
    def test_only_google_key_is_sufficient(self):
        self.assertEqual(
            available_providers({"GOOGLE_API_KEY": "a-private-value"}),
            ("Google Gemini (hesap kotası uygulanır)",),
        )

    def test_only_groq_key_is_sufficient(self):
        self.assertEqual(
            available_providers({"GROQ_API_KEY": "a-private-value"}),
            ("Groq GPT-OSS (sağlayıcı kotası uygulanır)",),
        )

    def test_openrouter_is_listed_only_when_its_key_is_present(self):
        self.assertEqual(
            available_providers({"OPENROUTER_API_KEY": "private"}),
            ("OpenRouter ücretsiz model havuzu (50 istek/gün sınırı)",),
        )

    def test_missing_or_blank_keys_are_not_available(self):
        self.assertEqual(available_providers({}), ())
        self.assertEqual(available_providers({"GOOGLE_API_KEY": "   "}), ())

    def test_local_models_are_available_without_credentials(self):
        self.assertEqual(
            available_providers({}, ["qwen3:8b"]),
            ("Ollama (Yerel): qwen3:8b",),
        )

    def test_unavailable_secret_storage_is_graceful(self):
        class NoFile:
            def __getitem__(self, key):
                raise FileNotFoundError("No secrets file")
        self.assertEqual(available_providers(NoFile()), ())


if __name__ == "__main__":
    unittest.main()

