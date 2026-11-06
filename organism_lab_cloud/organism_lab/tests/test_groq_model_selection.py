import json
import os
import unittest
from unittest.mock import patch
from organism_lab.providers import GROQ_MODEL_OPTIONS, ProviderError, generate

class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size=-1):
        data = json.dumps(self.payload).encode()
        return data if size < 0 else data[:size]

class GroqModelSelectionTests(unittest.TestCase):
    def test_model_allowlist_is_bounded_and_selectable(self):
        self.assertIn("openai/gpt-oss-120b", GROQ_MODEL_OPTIONS)
        captured = {}
        def sender(request, timeout):
            captured["body"] = json.loads(request.data.decode())
            return FakeResponse({"choices": [{"message": {"content": "ok"}}]})
        with patch.dict(os.environ, {"GROQ_API_KEY": "placeholder"}):
            result = generate("question", "groq", model="openai/gpt-oss-120b",
                              system_prompt="validator role", transport=sender)
        self.assertEqual(result["text"], "ok")
        self.assertEqual(captured["body"]["model"], "openai/gpt-oss-120b")
        self.assertEqual(captured["body"]["messages"][0],
                         {"role": "system", "content": "validator role"})

    def test_unapproved_model_is_rejected_before_network(self):
        called = False
        def sender(*args, **kwargs):
            nonlocal called
            called = True
        with patch.dict(os.environ, {"GROQ_API_KEY": "placeholder"}):
            with self.assertRaises(ValueError):
                generate("question", "groq", model="attacker/model", transport=sender)
        self.assertFalse(called)

    def test_provider_error_does_not_echo_secret(self):
        secret = "gsk_private_test_secret"
        def sender(*args, **kwargs): raise OSError(secret)
        with patch.dict(os.environ, {"GROQ_API_KEY": secret}):
            with self.assertRaises(ProviderError) as caught:
                generate("question", "groq", transport=sender)
        self.assertNotIn(secret, str(caught.exception))
