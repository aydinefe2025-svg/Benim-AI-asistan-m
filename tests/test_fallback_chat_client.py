import unittest
from core.fallback_chat_client import FallbackChatClient


class FakeClient:
    def __init__(self, result="ok", error=None):
        self.result, self.error, self.calls = result, error, []
    def chat(self, model, system, prompt, *, temperature=0.2):
        self.calls.append((model, system, prompt, temperature))
        if self.error: raise self.error
        return self.result


class FallbackChatClientTests(unittest.TestCase):
    def test_external_fallback_is_disabled_by_default_and_error_is_sanitized(self):
        primary = FakeClient(error=TimeoutError("private endpoint token")); fallback = FakeClient()
        client = FallbackChatClient(primary, fallback=fallback, fallback_model="remote")
        with self.assertRaisesRegex(RuntimeError, "TimeoutError") as error:
            client.chat("local", "system", "prompt")
        self.assertNotIn("private endpoint token", str(error.exception))
        self.assertEqual(len(primary.calls), 1); self.assertEqual(fallback.calls, [])

    def test_enabled_fallback_activates_once_and_stays_pinned_for_the_run(self):
        primary = FakeClient(error=TimeoutError("slow local model")); fallback = FakeClient("remote result")
        client = FallbackChatClient(primary, fallback=fallback, fallback_model="remote-model", allow_fallback=True)
        first = client.chat("local-model", "system", "first")
        second = client.chat("local-model", "system", "second")
        self.assertEqual((first, second), ("remote result", "remote result"))
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual([call[0] for call in fallback.calls], ["remote-model", "remote-model"])
        self.assertEqual(client.last_model_used, "remote-model")
        self.assertEqual(client.fallback_reason, "TimeoutError")

    def test_failed_fallback_has_no_provider_details_or_retry(self):
        primary = FakeClient(error=OSError("database password")); fallback = FakeClient(error=RuntimeError("api-secret-value"))
        client = FallbackChatClient(primary, fallback=fallback, fallback_model="remote", allow_fallback=True)
        with self.assertRaisesRegex(RuntimeError, "RuntimeError") as error:
            client.chat("local", "system", "prompt")
        self.assertNotIn("database password", str(error.exception)); self.assertNotIn("api-secret-value", str(error.exception))
        self.assertEqual(len(primary.calls), 1); self.assertEqual(len(fallback.calls), 1)

    def test_enabled_fallback_requires_a_client_and_model(self):
        with self.assertRaises(ValueError): FallbackChatClient(FakeClient(), allow_fallback=True)


if __name__ == "__main__": unittest.main()
