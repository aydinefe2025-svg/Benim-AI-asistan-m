import os
import unittest
from unittest.mock import patch

from core.provider_config import available_providers, configured_credentials


class ProviderEnvironmentTests(unittest.TestCase):
    def test_environment_fallback(self):
        creds = configured_credentials({}, {"GROQ_API_KEY": " test-token "})
        self.assertEqual(creds["GROQ_API_KEY"], "test-token")
        self.assertEqual(len(available_providers(creds)), 1)

    def test_streamlit_secret_precedence(self):
        creds = configured_credentials(
            {"GOOGLE_API_KEY": "streamlit-token"},
            {"GOOGLE_API_KEY": "environment-token"},
        )
        self.assertEqual(creds["GOOGLE_API_KEY"], "streamlit-token")

    def test_empty_secret_falls_back_to_environment(self):
        creds = configured_credentials({"GROQ_API_KEY": "  "}, {"GROQ_API_KEY": "fallback"})
        self.assertEqual(creds["GROQ_API_KEY"], "fallback")

    def test_no_credentials(self):
        self.assertEqual(configured_credentials({}, {}), {})
        self.assertEqual(available_providers({}), ())


if __name__ == "__main__":
    unittest.main()
