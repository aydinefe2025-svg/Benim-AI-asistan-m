import json
import unittest
import urllib.error
from unittest.mock import patch

from core.openrouter_free_client import OpenRouterError, OpenRouterFreeClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class OpenRouterFreeClientTests(unittest.TestCase):
    def test_request_is_forced_to_free_pool_and_caps_output(self):
        body = json.dumps({
            "model": "vendor/model-free:free",
            "choices": [{"message": {"content": "Merhaba"}}],
        }).encode()
        client = OpenRouterFreeClient("secret-test-key", max_output_tokens=320)
        with patch("urllib.request.urlopen", return_value=FakeResponse(body)) as call:
            answer = client.chat("paid/model-name", "system", "question")
        request = call.call_args.args[0]
        payload = json.loads(request.data.decode())
        self.assertEqual(payload["model"], "openrouter/free")
        self.assertEqual(payload["max_tokens"], 320)
        self.assertEqual(answer, "Merhaba")
        self.assertEqual(client.last_model_used, "vendor/model-free:free")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-test-key")

    def test_provider_errors_never_expose_key_or_response_body(self):
        client = OpenRouterFreeClient("secret-test-key")
        error = urllib.error.HTTPError(
            client.endpoint, 401, "unauthorized", {}, None
        )
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(OpenRouterError) as result:
                client.chat("openrouter/free", "system", "prompt")
        self.assertNotIn("secret-test-key", str(result.exception))
        self.assertNotIn("unauthorized", str(result.exception))
        self.assertEqual(result.exception.status_code, 401)

    def test_invalid_provider_response_is_classified_without_details(self):
        client = OpenRouterFreeClient("secret-test-key")
        with patch("urllib.request.urlopen", return_value=FakeResponse(b"{}")):
            with self.assertRaises(OpenRouterError) as result:
                client.chat("openrouter/free", "system", "prompt")
        self.assertEqual(result.exception.failure_kind, "response")
        self.assertNotIn("secret-test-key", str(result.exception))

    def test_invalid_credentials_and_output_limit_are_rejected(self):
        with self.assertRaises(ValueError):
            OpenRouterFreeClient(" ")
        with self.assertRaises(ValueError):
            OpenRouterFreeClient("key", max_output_tokens=0)


if __name__ == "__main__":
    unittest.main()

