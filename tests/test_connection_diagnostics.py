import json
import unittest
from unittest.mock import Mock

from core.connection_diagnostics import check_provider


class ConnectionDiagnosticTests(unittest.TestCase):
    def test_missing_credential_never_makes_network_request(self):
        request = Mock()
        self.assertEqual(check_provider('groq', '', request_get=request)['status'], 'not_configured')
        request.assert_not_called()

    def test_model_list_authentication_without_generation(self):
        request = Mock(return_value=Mock(status_code=200, json=lambda: {'data': [{'id': 'target'}]}))
        result = check_provider('groq', 'private-token', model='target', request_get=request)
        self.assertEqual(result['status'], 'verified')
        self.assertTrue(result['model_available'])
        self.assertEqual(request.call_args.args[0], 'https://api.groq.com/openai/v1/models')
        self.assertFalse(request.call_args.kwargs['allow_redirects'])

    def test_google_header_auth_and_paginated_missing_model(self):
        request = Mock(return_value=Mock(status_code=200, json=lambda: {'models': [], 'nextPageToken': 'page2'}))
        result = check_provider('google', 'private-token', model='target', request_get=request)
        self.assertEqual(result['status'], 'unverified')
        self.assertNotIn('private-token', request.call_args.args[0])
        self.assertEqual(request.call_args.kwargs['headers']['x-goog-api-key'], 'private-token')

    def test_model_name_prefix_normalized(self):
        request = Mock(return_value=Mock(status_code=200, json=lambda: {'models': [{'name': 'models/target'}]}))
        self.assertTrue(check_provider('google', 'token', model='target', request_get=request)['model_available'])

    def test_errors_do_not_leak_tokens_or_exception_text(self):
        request = Mock(side_effect=RuntimeError('https://api.telegram.org/botprivate-token/getMe'))
        result = check_provider('telegram', 'private-token', request_get=request)
        self.assertEqual(result['status'], 'unreachable_or_invalid')
        self.assertNotIn('private-token', json.dumps(result))

    def test_telegram_identity_only_no_messages(self):
        request = Mock(return_value=Mock(status_code=200, json=lambda: {'ok': True, 'result': {'is_bot': True}}))
        self.assertEqual(check_provider('telegram', 'token', request_get=request)['status'], 'verified')
        self.assertTrue(request.call_args.args[0].endswith('/getMe'))

    def test_auth_failure_and_redirect_are_not_success(self):
        for code in [301, 401, 403, 429, 500]:
            request = Mock(return_value=Mock(status_code=code))
            self.assertEqual(check_provider('google', 'token', request_get=request)['status'], 'failed')

    def test_malformed_body_is_not_success(self):
        request = Mock(return_value=Mock(status_code=200, json=lambda: {'models': 'invalid'}))
        self.assertEqual(check_provider('google', 'token', request_get=request)['status'], 'unreachable_or_invalid')

    def test_openrouter_read_only_authentication_check(self):
        request = Mock(return_value=Mock(status_code=200, json=lambda: {'data': [{'id': 'openrouter/free'}]}))
        result = check_provider('openrouter', 'private-token', request_get=request)
        self.assertEqual(result, {'status': 'verified', 'reachable': True, 'authenticated': True})
        self.assertEqual(request.call_args.args[0], 'https://openrouter.ai/api/v1/models')
        self.assertEqual(request.call_args.kwargs['headers']['Authorization'], 'Bearer private-token')
        self.assertFalse(request.call_args.kwargs['allow_redirects'])

    def test_openrouter_auth_and_quota_failures_are_classified_without_leaks(self):
        for code, expected in ((401, 'failed'), (403, 'failed'), (429, 'failed'), (503, 'failed')):
            request = Mock(return_value=Mock(status_code=code, text='private-token'))
            result = check_provider('openrouter', 'private-token', request_get=request)
            self.assertEqual(result['status'], expected)
            self.assertEqual(result['http_status'], code)
            self.assertNotIn('private-token', json.dumps(result))

    def test_openrouter_missing_key_and_malformed_body(self):
        request = Mock()
        self.assertEqual(check_provider('openrouter', '', request_get=request)['status'], 'not_configured')
        request.assert_not_called()
        malformed = Mock(return_value=Mock(status_code=200, json=lambda: {'data': 'invalid'}))
        self.assertEqual(check_provider('openrouter', 'token', request_get=malformed)['status'],
                         'unreachable_or_invalid')
