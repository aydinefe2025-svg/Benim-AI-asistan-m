import json
import os
import unittest
from io import BytesIO
from urllib.error import HTTPError, URLError
from unittest.mock import patch
from organism_lab.providers import (ProviderError, diagnose_groq_access, generate,
                                    groq_active_key, groq_test_key, trained_local_ready)

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
    def test_separate_test_key_is_inert_until_explicit_activation(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "existing-key",
                                     "GROQ_API_KEY_TEST": "candidate-key",
                                     "GROQ_API_KEY_TEST_ACTIVE": "0"}):
            self.assertEqual(groq_test_key(), "candidate-key")
            self.assertEqual(groq_active_key(), "existing-key")
    def test_separate_test_key_can_be_activated_without_replacing_existing_key(self):
        captured = {}
        def sender(request, timeout):
            captured["authorization"] = request.get_header("Authorization")
            return FakeResponse({"choices": [{"message": {"content": "OK"}}]})
        with patch.dict(os.environ, {"GROQ_API_KEY": "existing-key",
                                     "GROQ_API_KEY_TEST": "candidate-key",
                                     "GROQ_API_KEY_TEST_ACTIVE": "1"}):
            result = generate("hello", "groq", transport=sender)
            self.assertEqual(os.environ["GROQ_API_KEY"], "existing-key")
        self.assertEqual(result["text"], "OK")
        self.assertEqual(captured["authorization"], "Bearer candidate-key")
    def test_groq_trims_surrounding_key_whitespace(self):
        captured = {}
        def sender(request, timeout):
            captured["authorization"] = request.get_header("Authorization")
            return FakeResponse({"choices": [{"message": {"content": "OK"}}]})
        with patch.dict(os.environ, {"GROQ_API_KEY": "  test-placeholder\n"}):
            result = generate("hello", "groq", transport=sender)
        self.assertEqual(result["text"], "OK")
        self.assertEqual(captured["authorization"], "Bearer test-placeholder")

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

    def test_groq_403_falls_back_to_safe_error_type_when_code_is_absent(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-placeholder"}):
            def sender(request, timeout):
                body = json.dumps({"error": {
                    "type": "permissions_error",
                    "message": "DO_NOT_EXPOSE private permission detail",
                }}).encode()
                raise HTTPError(request.full_url, 403, "provider failure", None, BytesIO(body))
            with self.assertRaises(ProviderError) as raised:
                generate("hello", "groq", transport=sender)
        self.assertIn("erişimi reddedildi", str(raised.exception))
        self.assertIn("permissions_error", str(raised.exception))
        self.assertNotIn("DO_NOT_EXPOSE", str(raised.exception))
        self.assertNotIn("private permission detail", str(raised.exception))

    def test_groq_unstructured_403_is_classified_without_exposing_body(self):
        for body, classification in (
            (b"<html>DO_NOT_EXPOSE gateway denial</html>", "non_json_error_response"),
            (b'{"error":{"message":"DO_NOT_EXPOSE private text"}}',
             "json_error_without_machine_code"),
        ):
            with self.subTest(classification=classification), patch.dict(
                    os.environ, {"GROQ_API_KEY": "test-placeholder"}):
                def sender(request, timeout):
                    raise HTTPError(request.full_url, 403, "provider failure", None, BytesIO(body))
                with self.assertRaises(ProviderError) as raised:
                    generate("hello", "groq", transport=sender)
                self.assertIn(classification, str(raised.exception))
                self.assertNotIn("DO_NOT_EXPOSE", str(raised.exception))

    def test_groq_model_permission_codes_are_safely_exposed(self):
        for code in ("model_permission_blocked_org", "model_permission_blocked_project"):
            with self.subTest(code=code), patch.dict(os.environ, {"GROQ_API_KEY": "test-placeholder"}):
                def sender(request, timeout):
                    body = json.dumps({"error": {
                        "code": code,
                        "message": "DO_NOT_EXPOSE private model permission details",
                    }}).encode()
                    raise HTTPError(request.full_url, 403, "provider failure", None, BytesIO(body))
                with self.assertRaises(ProviderError) as raised:
                    generate("hello", "groq", transport=sender)
                self.assertIn(code, str(raised.exception))
                self.assertNotIn("DO_NOT_EXPOSE", str(raised.exception))
                self.assertNotIn("private model permission details", str(raised.exception))

    def test_groq_403_reads_nested_safe_machine_code(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-placeholder"}):
            def sender(request, timeout):
                body = json.dumps({"error": {"details": {"reason": {
                    "code": "model_permission_blocked_project",
                    "message": "DO_NOT_EXPOSE private account text",
                }}}}).encode()
                raise HTTPError(request.full_url, 403, "provider failure", None, BytesIO(body))
            with self.assertRaises(ProviderError) as raised:
                generate("hello", "groq", transport=sender)
        self.assertIn("model_permission_blocked_project", str(raised.exception))
        self.assertNotIn("private account text", str(raised.exception))

    def test_groq_access_diagnostic_checks_key_scoped_model_list(self):
        captured = {}
        def sender(request, timeout):
            captured["url"] = request.full_url
            captured["authorization"] = request.get_header("Authorization")
            return FakeResponse({"data": [{"id": "openai/gpt-oss-120b"}]})
        result = diagnose_groq_access("test-placeholder", "openai/gpt-oss-120b",
                                      transport=sender)
        self.assertEqual(captured["url"], "https://api.groq.com/openai/v1/models")
        self.assertEqual(captured["authorization"], "Bearer test-placeholder")
        self.assertEqual(result, {"reachable": True, "model_available": True,
                                  "http_status": 200, "error_code": None})

    def test_groq_access_diagnostic_returns_only_safe_error_metadata(self):
        def sender(request, timeout):
            body = json.dumps({"error": {"code": "invalid_project",
                                          "message": "DO_NOT_EXPOSE secret detail"}}).encode()
            raise HTTPError(request.full_url, 403, "denied", None, BytesIO(body))
        result = diagnose_groq_access("test-placeholder", "openai/gpt-oss-120b",
                                      transport=sender)
        self.assertEqual(result, {"reachable": False, "model_available": False,
                                  "http_status": 403, "error_code": "invalid_project"})
        self.assertNotIn("secret detail", repr(result))

    def test_groq_network_error_is_reported_safely(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-placeholder"}):
            with self.assertRaisesRegex(ProviderError, "Groq network request failed"):
                generate("hello", "groq", transport=lambda *args, **kwargs: (_ for _ in ()).throw(URLError("private detail")))


