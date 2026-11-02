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
