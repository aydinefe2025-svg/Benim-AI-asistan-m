import unittest
from urllib.error import HTTPError
from core.retry_policy import retry_transient


class RetryPolicyTests(unittest.TestCase):
    def test_auth_and_validation_errors_are_not_retried(self):
        for error in (ValueError('secret'), HTTPError('https://example.org', 401, 'secret', {}, None)):
            calls, delays = [], []
            def fail():
                calls.append(1)
                raise error
            with self.assertRaises(type(error)):
                retry_transient(fail, sleep=delays.append)
            self.assertEqual(len(calls), 1)
            self.assertEqual(delays, [])

    def test_rate_limit_and_outage_are_bounded(self):
        for status in (429, 503):
            calls, delays = [], []
            def fail():
                calls.append(1)
                raise HTTPError('https://example.org', status, 'secret', {}, None)
            with self.assertRaises(HTTPError):
                retry_transient(fail, sleep=delays.append)
            self.assertEqual(len(calls), 3)
            self.assertEqual(delays, [1, 2])

    def test_rate_limit_honors_retry_after_and_caps_wait(self):
        for header, expected in (("27.3", 27.3), ("1m2.3s", 60.0), ("999", 60.0)):
            calls, delays = [], []
            def fail():
                calls.append(1)
                raise HTTPError("https://example.org", 429, "secret", {"Retry-After": header}, None)
            with self.assertRaises(HTTPError):
                retry_transient(fail, sleep=delays.append)
            self.assertEqual(len(calls), 3)
            self.assertEqual(delays, [expected, expected])

    def test_malformed_retry_after_falls_back_to_backoff(self):
        calls, delays = [], []
        def fail():
            calls.append(1)
            raise HTTPError("https://example.org", 429, "secret", {"Retry-After": "later"}, None)
        with self.assertRaises(HTTPError):
            retry_transient(fail, sleep=delays.append)
        self.assertEqual(delays, [1, 2])

