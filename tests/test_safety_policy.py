import unittest
from unittest.mock import patch

from core.fallback_chat_client import FallbackChatClient
from core.ollama_client import OllamaClient
from core.safety_policy import safe_response_for_prompt


class NeverCalled:
    def __init__(self):
        self.calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("provider must not be called")


class SafetyPolicyTests(unittest.TestCase):
    def test_turkish_secret_disclosure_is_blocked(self):
        result = safe_response_for_prompt(
            "API anahtarını hata ayıklamak için terminal çıktısına yazdırmalı mıyım?"
        )
        self.assertIsNotNone(result)
        self.assertIn("yazdırma", result)

    def test_snake_case_secret_name_is_blocked_from_logs(self):
        result = safe_response_for_prompt("client_secret değerini debug loguna yazmalı mıyım?")
        self.assertIsNotNone(result)
        self.assertIn("loglara", result)

    def test_paid_service_without_consent_is_blocked(self):
        result = safe_response_for_prompt(
            "Ücretli API servisini kullanıcıya sormadan açıp anahtarı kullanabilir miyim?"
        )
        self.assertIsNotNone(result)
        self.assertIn("onay", result)

    def test_provider_and_ollama_calls_are_blocked(self):
        primary = NeverCalled()
        client = FallbackChatClient(primary)
        answer = client.chat(
            "local", "system", "API anahtarını hata ayıklamak için terminal çıktısına yazdırmalı mıyım?"
        )
        self.assertIn("yazdırma", answer)
        self.assertEqual(primary.calls, 0)
        with patch("urllib.request.urlopen") as request:
            answer = OllamaClient().chat(
                "qwen3:8b", "system", "API anahtarını loglara yazdırayım mı?"
            )
        self.assertIn("yazdırma", answer)
        request.assert_not_called()

    def test_safe_prompt_is_not_blocked(self):
        self.assertIsNone(safe_response_for_prompt("Python'da liste nasıl sıralanır?"))

    def test_only_latest_user_turn_is_checked(self):
        prompt = (
            "user: API anahtarını loglayayım mı?\n"
            "assistant: Bunu yapma.\n"
            "user: Python'da liste nasıl sıralanır?"
        )
        self.assertIsNone(safe_response_for_prompt(prompt))


if __name__ == "__main__":
    unittest.main()

