import unittest
from core.provider_failure import (copy_safe_failure_metadata, failure_category,
                                   failure_diagnostics, safe_failure_message)
from core.openrouter_free_client import OpenRouterError


class GoogleSdkError(Exception):
    def __init__(self, code, body=None):
        super().__init__("SECRET_VALUE provider text")
        self.code = code
        self.body = body


class ProviderFailureTests(unittest.TestCase):
    def test_failures_are_distinct_and_never_echo_provider_content(self):
        for status, category in ((401, "authentication"), (403, "permission"),
                                 (429, "rate_limit"), (404, "model"),
                                 (400, "request"), (503, "service"), (504, "network")):
            with self.subTest(status=status):
                error = RuntimeError("SECRET_VALUE provider text")
                error.status_code = status
                error.body = {"message": "SECRET_VALUE"}
                self.assertEqual(failure_category(error), category)
                self.assertNotIn("SECRET_VALUE", safe_failure_message(error))

    def test_google_sdk_numeric_code_is_classified_without_leaking_body(self):
        for code, category in ((401, "authentication"), (403, "permission"),
                               (429, "rate_limit"), (404, "model"),
                               (400, "request"), (503, "service")):
            with self.subTest(code=code):
                error = GoogleSdkError(code, body={"message": "SECRET_VALUE"})
                self.assertEqual(failure_category(error), category)
                self.assertNotIn("SECRET_VALUE", safe_failure_message(error))

    def test_valid_status_code_takes_precedence_over_sdk_code(self):
        error = GoogleSdkError(429)
        error.status_code = 401
        self.assertEqual(failure_category(error), "authentication")

    def test_rate_limit_machine_code_overrides_gateway_413(self):
        for code in ("rate_limit_exceeded", "insufficient_quota"):
            with self.subTest(code=code):
                error = RuntimeError("PRIVATE provider response")
                error.status_code = 413
                error.body = {"error": {"code": code, "message": "PRIVATE"}}
                self.assertEqual(failure_category(error), "rate_limit")
                self.assertIn("kota", safe_failure_message(error))
                self.assertNotIn("PRIVATE", safe_failure_message(error))

                wrapped = RuntimeError("safe adapter wrapper")
                copy_safe_failure_metadata(error, wrapped)
                self.assertEqual(failure_category(wrapped), "rate_limit")
                self.assertEqual(failure_diagnostics(wrapped), (413, code))

    def test_invalid_or_arbitrary_code_is_ignored(self):
        for code in ("429", True, 999, "SECRET_VALUE", [], {}):
            with self.subTest(code=repr(code)):
                self.assertEqual(failure_category(GoogleSdkError(code)), "unknown")

    def test_safe_provider_diagnostics_allowlist_status_code_and_type(self):
        error = RuntimeError("PRIVATE provider response")
        error.status_code = 400
        error.body = {"error": {"type": "invalid_request_error", "message": "PRIVATE"}}
        self.assertEqual(failure_diagnostics(error), (400, "invalid_request_error"))
        error.body["error"]["type"] = "PRIVATE provider text"
        self.assertEqual(failure_diagnostics(error), (400, None))
        error.body["error"]["type"] = {}
        self.assertEqual(failure_diagnostics(error), (400, None))

    def test_safe_provider_diagnostics_prioritizes_allowlisted_code(self):
        error = RuntimeError("PRIVATE provider response")
        error.body = {"error": {"code": "unsupported_parameter",
                                "type": "invalid_request_error"}}
        self.assertEqual(failure_diagnostics(error), (None, "unsupported_parameter"))

    def test_model_retirement_machine_code(self):
        error = RuntimeError("private")
        error.status_code = 400
        error.body = {"error": {"code": "model_decommissioned"}}
        self.assertEqual(failure_category(error), "model")

    def test_network_and_unknown_errors(self):
        self.assertEqual(failure_category(TimeoutError()), "network")
        self.assertEqual(failure_category(ConnectionError()), "network")
        self.assertEqual(failure_category(RuntimeError("private")), "unknown")

    def test_openrouter_error_categories_are_safe(self):
        self.assertEqual(failure_category(OpenRouterError("safe", status_code=401)), "authentication")
        self.assertEqual(failure_category(OpenRouterError("safe", status_code=429)), "rate_limit")
        self.assertEqual(failure_category(OpenRouterError("safe", failure_kind="network")), "network")
        self.assertEqual(failure_category(OpenRouterError("safe", failure_kind="response")), "response")

    def test_safe_error_parameter_survives_wrapping_without_provider_body(self):
        from core import provider_failure as m
        self.assertTrue(callable(getattr(m, "safe_failure_param", None)))
        class SyntheticError(Exception):
            status_code = 400
            body = {"error": {"type": "invalid_request_error",
                              "param": "temperature",
                              "message": "PRIVATE key or request content"}}
        incoming = SyntheticError("PRIVATE provider details")
        wrapped = RuntimeError("safe wrapper")
        copy_safe_failure_metadata(incoming, wrapped)
        self.assertEqual(m.safe_failure_param(wrapped), "temperature")
        self.assertEqual(failure_diagnostics(wrapped), (400, "invalid_request_error"))
        self.assertNotIn("PRIVATE", repr(wrapped))

    def test_unknown_parameter_is_not_emitted_as_diagnostic(self):
        from core import provider_failure as m
        self.assertTrue(callable(getattr(m, "safe_failure_param", None)))
        error = RuntimeError("PRIVATE")
        error.param = "CANO_SECRET_RAW_OWNER_EMAIL"
        error.body = {"error": {"param": "CANO_SECRET_RAW_OWNER_EMAIL"}}
        self.assertIsNone(m.safe_failure_param(error))
        for expected in ("model", "messages", "max_tokens", "max_output_tokens"):
            error.param = expected
            self.assertEqual(m.safe_failure_param(error), expected)

    def test_malformed_body_is_safe(self):
        error = RuntimeError("private")
        error.body = {"error": ["private"]}
        self.assertEqual(failure_category(error), "unknown")


if __name__ == "__main__":
    unittest.main()
