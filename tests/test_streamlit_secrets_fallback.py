import unittest

from core.provider_config import (
    available_providers,
    configured_credentials,
    credential_presence,
)


class StreamlitSecretsFallbackTests(unittest.TestCase):
    def test_missing_streamlit_secrets_configuration_uses_environment(self):
        class StreamlitSecretNotFoundError(RuntimeError):
            pass

        class MissingSecrets:
            def __getitem__(self, key):
                raise StreamlitSecretNotFoundError("secrets are not configured")

        credentials = configured_credentials(
            MissingSecrets(),
            {"GROQ_API_KEY": "present"},
        )

        self.assertEqual(credentials, {"GROQ_API_KEY": "present"})
        self.assertEqual(len(available_providers(credentials)), 1)

    def test_secret_lookup_failure_does_not_block_environment_fallback(self):
        class BrokenSecrets:
            def __getitem__(self, key):
                raise RuntimeError("unavailable")

        credentials = configured_credentials(
            BrokenSecrets(),
            {"GOOGLE_API_KEY": "present"},
        )

        self.assertEqual(credential_presence(credentials), {
            "GROQ_API_KEY": False,
            "GOOGLE_API_KEY": True,
        })

    def test_diagnostics_contain_only_presence_flags(self):
        credentials = {"GROQ_API_KEY": "present"}
        diagnostic = credential_presence(credentials)

        self.assertEqual(diagnostic, {
            "GROQ_API_KEY": True,
            "GOOGLE_API_KEY": False,
        })
        self.assertNotIn("present", repr(diagnostic))


if __name__ == "__main__":
    unittest.main()
