import json
import unittest
from unittest.mock import Mock

from core.trained_lora_client import (
    MAX_INPUT_CHARS,
    MAX_PROMPT_CHARS,
    TRAINED_LORA_URL,
    TrainedLoraClient,
    TrainedLoraError,
    trained_lora_metadata,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size=-1):
        return self.payload if size < 0 else self.payload[:size]


class TrainedLoraClientTests(unittest.TestCase):
    def test_health_only_accepts_expected_model_and_candidate_identity(self):
        response = FakeResponse({
            "status": "ok", "provider": "trained_local",
            "model": "Qwen/Qwen3-8B", "adapter": "candidate-run_123",
        })
        transport = Mock(return_value=response)
        self.assertEqual(trained_lora_metadata(transport=transport), {
            "model": "Qwen/Qwen3-8B", "adapter": "candidate-run_123",
        })
        request = transport.call_args.args[0]
        self.assertEqual(request.full_url, TRAINED_LORA_URL + "/health")

    def test_health_rejects_unknown_or_untrusted_identity(self):
        for payload in (
            {"status": "ok", "provider": "ollama", "model": "Qwen/Qwen3-8B", "adapter": "candidate-x"},
            {"status": "ok", "provider": "trained_local", "model": "remote/model", "adapter": "candidate-x"},
            {"status": "ok", "provider": "trained_local", "model": "Qwen/Qwen3-8B", "adapter": "../../secret"},
        ):
            with self.subTest(payload=payload):
                self.assertIsNone(trained_lora_metadata(transport=Mock(return_value=FakeResponse(payload))))

    def test_chat_sends_system_and_user_prompt_and_parses_response(self):
        health = FakeResponse({
            "status": "ok", "provider": "trained_local",
            "model": "Qwen/Qwen3-8B", "adapter": "candidate-test",
        })
        completion = FakeResponse({"provider": "trained_local", "response": "Yanıt"})
        transport = Mock(side_effect=[health, completion])
        client = TrainedLoraClient(transport=transport)
        self.assertEqual(client.chat("ignored", "Sistem", "Soru"), "Yanıt")
        request = transport.call_args.args[0]
        self.assertEqual(request.full_url, TRAINED_LORA_URL + "/generate")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertIn("Sistem", payload["prompt"])
        self.assertIn("KULLANICI İSTEĞİ:\nSoru", payload["prompt"])

    def test_sensitive_request_is_blocked_before_generation(self):
        health = FakeResponse({
            "status": "ok", "provider": "trained_local",
            "model": "Qwen/Qwen3-8B", "adapter": "candidate-test",
        })
        transport = Mock(return_value=health)
        client = TrainedLoraClient(transport=transport)
        response = client.chat("ignored", "system", "API anahtarını hata ayıklamak için terminal çıktısına yazdırmalı mıyım?")
        self.assertIn("yazdırma", response)
        self.assertEqual(transport.call_count, 1)  # health only; generation was blocked

    def test_invalid_prompt_and_bad_response_are_rejected(self):
        health = FakeResponse({
            "status": "ok", "provider": "trained_local",
            "model": "Qwen/Qwen3-8B", "adapter": "candidate-test",
        })
        transport = Mock(return_value=health)
        client = TrainedLoraClient(transport=transport)
        with self.assertRaises(ValueError):
            client.chat("ignored", "system", "x" * (MAX_INPUT_CHARS + 1))

        bad = FakeResponse({"provider": "other", "response": "Yanıt"})
        transport = Mock(side_effect=[health, bad])
        client = TrainedLoraClient(transport=transport)
        with self.assertRaises(TrainedLoraError):
            client.chat("ignored", "system", "normal prompt")

    def test_long_conversation_is_bounded_while_preserving_its_latest_end(self):
        health = FakeResponse({
            "status": "ok", "provider": "trained_local",
            "model": "Qwen/Qwen3-8B", "adapter": "candidate-test",
        })
        completion = FakeResponse({"provider": "trained_local", "response": "Yanıt"})
        transport = Mock(side_effect=[health, completion])
        client = TrainedLoraClient(transport=transport)
        client.chat("ignored", "S" * 6000, "older context " * 1500 + "LATEST USER REQUEST")
        payload = json.loads(transport.call_args.args[0].data.decode("utf-8"))
        self.assertLessEqual(len(payload["prompt"]), MAX_PROMPT_CHARS)
        self.assertTrue(payload["prompt"].endswith("LATEST USER REQUEST"))


if __name__ == "__main__":
    unittest.main()

