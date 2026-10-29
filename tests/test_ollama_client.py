import json
import unittest
import urllib.error
from unittest.mock import patch

from core.ollama_client import OllamaClient, OllamaError


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class OllamaClientTests(unittest.TestCase):
    def test_list_models_parses_tags(self):
        response = FakeResponse(json.dumps({
            "models": [{"name": "qwen3:8b"}, {"name": "tinyllama:latest"}]
        }).encode())
        with patch("urllib.request.urlopen", return_value=response):
            self.assertEqual(
                OllamaClient().list_models(),
                ["qwen3:8b", "tinyllama:latest"],
            )

    def test_chat_parses_content(self):
        response = FakeResponse(json.dumps({
            "message": {"content": "  Araştırma taslağı  "}
        }).encode())
        with patch("urllib.request.urlopen", return_value=response) as mocked:
            answer = OllamaClient().chat("qwen3:8b", "system", "question")
        self.assertEqual(answer, "Araştırma taslağı")
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        payload = json.loads(request.data.decode())
        self.assertEqual(payload["model"], "qwen3:8b")
        self.assertFalse(payload["stream"])

    def test_http_errors_keep_status_and_body(self):
        error = urllib.error.HTTPError(
            "http://127.0.0.1:11434/api/tags", 404, "not found", {}, None
        )
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(OllamaError, "HTTP 404"):
                OllamaClient().list_models()


if __name__ == "__main__":
    unittest.main()
