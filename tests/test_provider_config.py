"""Credentials must be checked independently and never printed."""
import unittest
from core.provider_config import available_providers


class ProviderConfigTests(unittest.TestCase):
    def test_only_google_key_is_sufficient(self):
        self.assertEqual(
            available_providers({"GOOGLE_API_KEY": "a-private-value"}),
            ("Google Gemini (Gelişmiş Mod)",),
        )

    def test_only_groq_key_is_sufficient(self):
        self.assertEqual(
            available_providers({"GROQ_API_KEY": "a-private-value"}),
            ("Groq GPT-OSS (Hızlı / Kesintisiz)",),
        )

    def test_missing_or_blank_keys_are_not_available(self):
        self.assertEqual(available_providers({}), ())
        self.assertEqual(available_providers({"GOOGLE_API_KEY": "   "}), ())

    def test_unavailable_secret_storage_is_graceful(self):
        class NoFile:
            def __getitem__(self, key):
                raise FileNotFoundError("No secrets file")
        self.assertEqual(available_providers(NoFile()), ())


if __name__ == "__main__":
    unittest.main()
