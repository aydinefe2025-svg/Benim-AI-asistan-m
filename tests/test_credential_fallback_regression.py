"""Regression coverage for Render environment fallback; no real credentials used."""
import unittest

from core.provider_config import configured_credentials, credential_presence, available_providers


class MissingSecrets:
    def __getitem__(self, key):
        raise FileNotFoundError("Secrets file not configured")


class CredentialFallbackTests(unittest.TestCase):
    def test_environment_fallback_when_secrets_missing(self):
        result = configured_credentials(MissingSecrets(), {"GROQ_API_KEY": " fake-groq "})
        self.assertEqual(result, {"GROQ_API_KEY": "fake-groq"})
        self.assertEqual(available_providers(result), ("Groq GPT-OSS (Hızlı / Kesintisiz)",))

    def test_blank_secret_does_not_mask_environment(self):
        result = configured_credentials({"GROQ_API_KEY": "  "}, {"GROQ_API_KEY": "fake-groq"})
        self.assertEqual(result["GROQ_API_KEY"], "fake-groq")

    def test_valid_secret_takes_precedence(self):
        result = configured_credentials({"GROQ_API_KEY": "fake-secret"}, {"GROQ_API_KEY": "fake-env"})
        self.assertEqual(result["GROQ_API_KEY"], "fake-secret")

    def test_blank_environment_does_not_enable_provider(self):
        result = configured_credentials(MissingSecrets(), {"GROQ_API_KEY": "   "})
        self.assertEqual(result, {})
        self.assertFalse(credential_presence(result)["GROQ_API_KEY"])

    def test_google_environment_alone_works(self):
        result = configured_credentials(MissingSecrets(), {"GOOGLE_API_KEY": "fake-google"})
        self.assertEqual(available_providers(result), ("Google Gemini (Gelişmiş Mod)",))


if __name__ == "__main__":
    unittest.main()
