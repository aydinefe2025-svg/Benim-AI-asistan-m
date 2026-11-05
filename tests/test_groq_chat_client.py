import sys
import types
import unittest
from unittest.mock import patch
from core.groq_chat_client import GroqChatClient


class GroqChatClientTests(unittest.TestCase):
    def test_request_uses_bounded_timeout_and_disables_retries(self):
        captured = {}
        class Completions:
            @staticmethod
            def create(**kwargs):
                captured["request"] = kwargs
                return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="  draft result  "))])
        class Groq:
            def __init__(self, **kwargs):
                captured["client"] = kwargs
                self.chat = types.SimpleNamespace(completions=Completions())
        with patch.dict(sys.modules, {"groq": types.SimpleNamespace(Groq=Groq)}):
            result = GroqChatClient("secret-value", timeout=4).chat("model", "system", "prompt")
        self.assertEqual(result, "draft result")
        self.assertEqual(captured["client"]["timeout"], 4.0)
        self.assertEqual(captured["client"]["max_retries"], 0)
        self.assertEqual(captured["request"]["model"], "model")

    def test_provider_error_details_are_not_exposed(self):
        class BrokenGroq:
            def __init__(self, **kwargs):
                self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=lambda **request: (_ for _ in ()).throw(RuntimeError("secret-value provider detail"))))
        with patch.dict(sys.modules, {"groq": types.SimpleNamespace(Groq=BrokenGroq)}):
            with self.assertRaisesRegex(RuntimeError, "RuntimeError") as error:
                GroqChatClient("secret-value").chat("model", "system", "prompt")
        self.assertNotIn("secret-value", str(error.exception)); self.assertNotIn("provider detail", str(error.exception))


if __name__ == "__main__": unittest.main()
