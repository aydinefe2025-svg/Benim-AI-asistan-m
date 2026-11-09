import unittest
from core.provider_failure import failure_category, failure_diagnostics, safe_failure_message
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

    def test_invalid_or_arbitrary_code_is_ignored(self):
        for code in ("429", True, 999, "SECRET_VALUE"):
            with self.subTest(code=code):
                self.assertEqual(failure_category(GoogleSdkError(code)), "unknown")

    def test_safe_provider_diagnostics_allowlist_status_and_code(self):
        error = RuntimeError("PRIVATE provider response")
        error.status_code = 400
        error.body = {"error": {"code": "unsupported_parameter", "message": "PRIVATE"}}
        self.assertEqual(failure_diagnostics(error), (400, "unsupported_parameter"))
        error.body["error"]["code"] = "PRIVATE provider text"
        self.assertEqual(failure_diagnostics(error), (400, None))

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

    def test_malformed_body_is_safe(self):
        error = RuntimeError("private")
        error.body = {"error": ["private"]}
        self.assertEqual(failure_category(error), "unknown")


if __name__ == "__main__":
    unittest.main()
