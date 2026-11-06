import unittest

from core.provider_router import (
    OPENROUTER_LABEL,
    build_provider_router,
    fallback_options,
)


class ProviderRouterTests(unittest.TestCase):
    def test_only_local_and_fixed_free_pool_are_fallbacks(self):
        credentials = {
            "GROQ_API_KEY": "groq-key",
            "GOOGLE_API_KEY": "google-key",
            "OPENROUTER_API_KEY": "openrouter-key",
        }
        options = fallback_options(
            "Groq GPT-OSS (sağlayıcı kotası uygulanır)", credentials,
            ["qwen3:8b"],
        )
        self.assertEqual(options, ("Yerel Ollama · qwen3:8b", OPENROUTER_LABEL))
        router = build_provider_router(
            "Groq GPT-OSS (sağlayıcı kotası uygulanır)", credentials,
            ["qwen3:8b"], allow_fallback=True,
        )
        self.assertTrue(router.allow_fallback)
        self.assertEqual([name for name, _, _ in router.fallback_chain],
                         ["Ollama (Yerel)", OPENROUTER_LABEL])
        self.assertEqual([model for _, _, model in router.fallback_chain][-1],
                         "openrouter/free")

    def test_fallback_is_off_by_default_even_when_several_providers_exist(self):
        router = build_provider_router(
            "Google Gemini (hesap kotası uygulanır)",
            {"GOOGLE_API_KEY": "google-key", "OPENROUTER_API_KEY": "openrouter-key"},
            ["qwen3:8b"],
        )
        self.assertFalse(router.allow_fallback)
        self.assertEqual(router.primary_provider, "Google Gemini")

    def test_local_primary_can_fail_over_only_after_opt_in(self):
        router = build_provider_router(
            "Ollama (Yerel): qwen3:8b",
            {"OPENROUTER_API_KEY": "openrouter-key"},
            ["qwen3:8b"], allow_fallback=True,
        )
        self.assertEqual(router.primary_provider, "Ollama (Yerel)")
        self.assertEqual([name for name, _, _ in router.fallback_chain], [OPENROUTER_LABEL])

    def test_unknown_or_unconfigured_provider_is_rejected(self):
        with self.assertRaises(ValueError):
            build_provider_router("Groq GPT-OSS", {})
        with self.assertRaises(ValueError):
            build_provider_router("not-a-provider", {})


if __name__ == "__main__":
    unittest.main()

