import unittest
from core.provider_failure import failure_category, safe_failure_message


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

    def test_model_retirement_machine_code(self):
        error = RuntimeError("private")
        error.status_code = 400
        error.body = {"error": {"code": "model_decommissioned"}}
        self.assertEqual(failure_category(error), "model")

    def test_network_and_unknown_errors(self):
        self.assertEqual(failure_category(TimeoutError()), "network")
        self.assertEqual(failure_category(ConnectionError()), "network")
        self.assertEqual(failure_category(RuntimeError("private")), "unknown")

    def test_malformed_body_is_safe(self):
        error = RuntimeError("private")
        error.body = {"error": ["private"]}
        self.assertEqual(failure_category(error), "unknown")
