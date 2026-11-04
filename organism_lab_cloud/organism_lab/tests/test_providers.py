import json
import os
import unittest
from io import BytesIO
from urllib.error import HTTPError, URLError
from unittest.mock import patch
from organism_lab.providers import ProviderError, generate, trained_local_ready

class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size=-1):
        data = json.dumps(self.payload).encode()
        return data if size < 0 else data[:size]

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
    def test_trained_local_mock(self):
        captured = {}
        def sender(request, timeout):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse({"provider": "trained_local", "response": "ADAPTER_OK"})
        result = generate("hello", "trained_local", transport=sender)
        self.assertEqual(result["text"], "ADAPTER_OK")
        self.assertEqual(captured["url"], "http://127.0.0.1:8765/generate")
        self.assertEqual(captured["payload"], {"prompt": "hello"})
        self.assertEqual(captured["timeout"], 240)
    def test_trained_local_health_check(self):
        self.assertTrue(trained_local_ready(transport=lambda req, timeout: FakeResponse(
            {"status": "ok", "provider": "trained_local"})))
        self.assertFalse(trained_local_ready(transport=lambda req, timeout: FakeResponse(
            {"status": "ok", "provider": "other"})))
    def test_ollama_disables_qwen_thinking_and_allows_model_load_time(self):
        captured = {}
        def sender(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse({"response": "LOCAL_OK"})
        result = generate("hello", "ollama", transport=sender)
        self.assertEqual(result["text"], "LOCAL_OK")
        self.assertFalse(captured["payload"]["think"])
        self.assertEqual(captured["timeout"], 120)
    def test_groq_missing_key(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            with self.assertRaises(ProviderError):
                generate("hello", "groq")
    def test_groq_mock(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-placeholder"}):
            result = generate("hello", "groq", transport=lambda req, timeout: FakeResponse({"choices": [{"message": {"content": "OK"}}]}))
        self.assertEqual(result["text"], "OK")
    def test_groq_rejects_untrusted_endpoint_before_sending_key(self):
        sender_called = False
        def sender(*args, **kwargs):
            nonlocal sender_called
            sender_called = True
            raise AssertionError("untrusted endpoint must not be contacted")
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-placeholder",
                                     "GROQ_API_URL": "https://attacker.example/collect"}):
            with self.assertRaisesRegex(ProviderError, "trusted HTTPS"):
                generate("hello", "groq", transport=sender)
        self.assertFalse(sender_called)
    def test_groq_rejects_malformed_endpoint_without_leaking_key(self):
        for endpoint in ("", "https://api.groq.com:99999/openai/v1/chat/completions"):
            with self.subTest(endpoint=endpoint), patch.dict(
                    os.environ, {"GROQ_API_KEY": "test-placeholder", "GROQ_API_URL": endpoint}):
                with self.assertRaisesRegex(ProviderError, "trusted HTTPS"):
                    generate("hello", "groq", transport=lambda *args, **kwargs: self.fail("sent"))
    def test_provider_response_size_is_bounded(self):
        class LargeResponse(FakeResponse):
            def read(self, size=-1):
                return b"x" * (size + 1)
        with self.assertRaisesRegex(ProviderError, "size limit"):
            generate("hello", "ollama", transport=lambda req, timeout: LargeResponse({}))
    def test_empty_model_response(self):
        with self.assertRaises(ProviderError):
            generate("hello", "ollama", transport=lambda req, timeout: FakeResponse({"response": ""}))


    def test_groq_http_errors_are_classified_without_exposing_provider_body(self):
        cases = {
            401: "geçersiz veya iptal edilmiş",
            403: "erişimi reddetti",
            404: "modeli veya isteği",
            429: "kota veya istek hızı",
            503: "geçici sunucu hatası",
        }
        for status, expected in cases.items():
            with self.subTest(status=status), patch.dict(os.environ, {"GROQ_API_KEY": "test-placeholder"}):
                def sender(request, timeout):
                    raise HTTPError(request.full_url, status, "provider failure",
                                    None, BytesIO(b"DO_NOT_EXPOSE_PROVIDER_BODY"))
                with self.assertRaises(ProviderError) as raised:
                    generate("hello", "groq", transport=sender)
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn("DO_NOT_EXPOSE_PROVIDER_BODY", str(raised.exception))

    def test_groq_403_exposes_only_allowlisted_provider_code(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-placeholder"}):
            def sender(request, timeout):
                body = json.dumps({"error": {
                    "code": "project_permission_denied",
                    "message": "DO_NOT_EXPOSE provider detail",
                }}).encode()
                raise HTTPError(request.full_url, 403, "provider failure", None, BytesIO(body))
            with self.assertRaises(ProviderError) as raised:
                generate("hello", "groq", transport=sender)
        self.assertIn("proje/organizasyon erişimi reddedildi", str(raised.exception))
        self.assertIn("project_permission_denied", str(raised.exception))
        self.assertNotIn("DO_NOT_EXPOSE", str(raised.exception))
        self.assertNotIn("provider detail", str(raised.exception))

    def test_groq_network_error_is_reported_safely(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-placeholder"}):
            with self.assertRaisesRegex(ProviderError, "Groq network request failed"):
                generate("hello", "groq", transport=lambda *args, **kwargs: (_ for _ in ()).throw(URLError("private detail")))

