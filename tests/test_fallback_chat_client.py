import unittest

from core.fallback_chat_client import FallbackChatClient


class FakeClient:
    def __init__(self, result="ok", error=None):
        self.result = result
        self.error = error
        self.calls = []

    def chat(self, model, system, prompt, *, temperature=0.2):
        self.calls.append((model, system, prompt, temperature))
        if self.error:
            raise self.error
        return self.result


class FallbackChatClientTests(unittest.TestCase):
    def test_external_fallback_is_disabled_by_default_and_error_is_sanitized(self):
        primary = FakeClient(error=TimeoutError("private endpoint token"))
        fallback = FakeClient()
        client = FallbackChatClient(primary, fallback=fallback, fallback_model="remote")

        with self.assertRaisesRegex(RuntimeError, "TimeoutError") as error:
            client.chat("local", "system", "prompt")

        self.assertNotIn("private endpoint token", str(error.exception))
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(fallback.calls, [])

    def test_sanitized_provider_status_survives_primary_wrapper(self):
        class ProviderError(RuntimeError):
            status_code = 429
            failure_kind = None

        primary = FakeClient(error=ProviderError("private provider body"))
        client = FallbackChatClient(primary)
        with self.assertRaises(RuntimeError) as caught:
            client.chat("free", "system", "prompt")

        self.assertEqual(caught.exception.failure_kind, "rate_limit")
        self.assertEqual(caught.exception.status_code, 429)
        self.assertNotIn("private provider body", str(caught.exception))

    def test_enabled_fallback_activates_once_and_stays_pinned_for_the_run(self):
        primary = FakeClient(error=TimeoutError("slow local model"))
        fallback = FakeClient(result="remote result")
        client = FallbackChatClient(
            primary, fallback=fallback, fallback_model="remote-model", allow_fallback=True
        )

        first = client.chat("local-model", "system", "first")
        second = client.chat("local-model", "system", "second")

        self.assertEqual((first, second), ("remote result", "remote result"))
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual([call[0] for call in fallback.calls], ["remote-model", "remote-model"])
        self.assertEqual(client.last_model_used, "remote-model")
        self.assertEqual(client.fallback_reason, "TimeoutError")

    def test_no_retry_and_failed_fallback_has_no_provider_details(self):
        primary = FakeClient(error=OSError("database password"))
        fallback = FakeClient(error=RuntimeError("api-secret-value"))
        client = FallbackChatClient(
            primary, fallback=fallback, fallback_model="remote", allow_fallback=True
        )

        with self.assertRaisesRegex(RuntimeError, "RuntimeError") as error:
            client.chat("local", "system", "prompt")

        self.assertNotIn("database password", str(error.exception))
        self.assertNotIn("api-secret-value", str(error.exception))
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(len(fallback.calls), 1)

    def test_enabled_fallback_requires_a_client_and_model(self):
        with self.assertRaises(ValueError):
            FallbackChatClient(FakeClient(), allow_fallback=True)

    def test_ordered_chain_skips_failed_provider_and_tracks_actual_provider(self):
        primary = FakeClient(error=TimeoutError("local timeout"))
        groq = FakeClient(error=RuntimeError("private groq detail"))
        google = FakeClient(result="gemini draft")
        client = FallbackChatClient(
            primary,
            fallback_chain=[
                ("Groq", groq, "groq-model"),
                ("Google Gemini", google, "gemini-model"),
            ],
            allow_fallback=True,
        )

        self.assertEqual(client.chat("local-model", "system", "prompt"), "gemini draft")
        self.assertEqual(client.last_provider_used, "Google Gemini")
        self.assertEqual(client.last_model_used, "gemini-model")
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(len(groq.calls), 1)
        self.assertEqual(len(google.calls), 1)

    def test_exhausted_chain_clears_stale_provider_tracking(self):
        primary = FakeClient(error=TimeoutError("local timeout"))
        groq = FakeClient(result="initial draft")
        google = FakeClient(error=RuntimeError("google unavailable"))
        client = FallbackChatClient(
            primary,
            fallback_chain=[("Groq", groq, "groq-model"),
                            ("Google Gemini", google, "gemini-model")],
            allow_fallback=True,
        )

        self.assertEqual(client.chat("local", "system", "first"), "initial draft")
        groq.error = TimeoutError("groq timeout")
        with self.assertRaisesRegex(RuntimeError, "All explicitly enabled"):
            client.chat("local", "system", "second")
        self.assertIsNone(client.last_provider_used)
        self.assertIsNone(client.last_model_used)


if __name__ == "__main__":
    unittest.main()

