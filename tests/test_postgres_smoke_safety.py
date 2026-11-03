from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

from scripts.check_postgres_persistence import main, require


class PostgresSmokeSafetyTests(unittest.TestCase):
    def test_no_config_is_explicit_failure_without_connecting(self):
        output = io.StringIO()
        with patch('sys.argv', ['check']), patch.dict('os.environ', {}, clear=True), \
                patch('scripts.check_postgres_persistence.run_checks') as run, redirect_stdout(output):
            self.assertEqual(main(), 2)
            run.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['status'], 'not_configured')

    def test_connection_error_does_not_disclose_url_or_password(self):
        secret_url = 'postgresql://example:private-password@example.invalid/db'
        output = io.StringIO()
        with patch('sys.argv', ['check', '--secure-prompt']), \
                patch('scripts.check_postgres_persistence.getpass.getpass', return_value=secret_url), \
                patch('scripts.check_postgres_persistence.run_checks', side_effect=RuntimeError(secret_url)), \
                redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertNotIn('private-password', output.getvalue())
        self.assertNotIn(secret_url, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['error_type'], 'RuntimeError')

    def test_verification_failure_is_explicit_even_without_asserts(self):
        with self.assertRaises(ValueError):
            require(False, 'Mismatch')
