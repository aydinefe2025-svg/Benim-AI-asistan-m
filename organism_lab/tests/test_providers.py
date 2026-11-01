import json
import os
import unittest
from unittest.mock import patch
from organism_lab.providers import ProviderError, generate

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.payload).encode()

class ProviderTests(unittest.TestCase):
    def test_offline_never_calls_network(self):
        self.assertEqual(generate("hello")["status"], "unavailable")
    def test_unknown_provider_rejected(self):
        with self.assertRaises(ValueError):
            generate("hello", "unknown")
    def test_empty_prompt_rejected(self):
        with self.assertRaises(ValueError):
            generate(" ", "offline")
    def test_ollama_mock(self):
        result = generate("hello", "ollama", transport=lambda req, timeout: FakeResponse({"response": "OK"}))
        self.assertEqual(result["text"], "OK")
    def test_groq_missing_key(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            with self.assertRaises(ProviderError):
                generate("hello", "groq")
    def test_groq_mock(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-placeholder"}):
            result = generate("hello", "groq", transport=lambda req, timeout: FakeResponse({"choices": [{"message": {"content": "OK"}}]}))
        self.assertEqual(result["text"], "OK")
    def test_empty_model_response(self):
        with self.assertRaises(ProviderError):
            generate("hello", "ollama", transport=lambda req, timeout: FakeResponse({"response": ""}))
