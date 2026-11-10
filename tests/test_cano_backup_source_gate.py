"""Offline failure-focused tests; never connect to production PostgreSQL."""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cano_backup_source_gate import (APP_SOURCE_PROFILES, require_application_source)


class ApplicationBackupSourceGateTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            'PGHOST': 'ep-cano.test.neon.tech',
            'PGDATABASE': 'assistant_pg',
            'PGUSER': 'operator',
            'PGPASSWORD': 'PRIVATE-PASSWORD',
            'CANO_BACKUP_KEY_HEX': 'SECRET-DO-NOT-FORWARD',
        }
        self.expected_host = 'ep-cano.test.neon.tech'
        self.required = APP_SOURCE_PROFILES['full']

    @staticmethod
    def row(name, tables, active):
        return SimpleNamespace(returncode=0, stdout=f'{name}\t{",".join(sorted(tables))}\t{int(active)}\n'.encode(), stderr=b'')

    def test_valid_source_returns_a_bound_safe_receipt(self):
        spy = Mock(return_value=self.row('assistant_pg', self.required, True))
        with patch('cano_backup_source_gate.shutil.which', return_value='/bin/psql'):
            result = require_application_source(self.env, 'full', expected_host=self.expected_host,
                                                expected_database='assistant_pg', runner=spy)
        self.assertEqual(result['profile'], 'full')
        self.assertEqual(result['required_tables_matched'], 9)
        self.assertTrue(result['nonempty_table_verified'])
        self.assertNotIn('PRIVATE-PASSWORD', str(result))
        self.assertNotIn('ep-cano.test.neon.tech', str(result))
        argv = spy.call_args.args[0]
        self.assertIn('--no-password', argv)
        self.assertIn('ON_ERROR_STOP=1', argv)
        self.assertNotIn('PRIVATE-PASSWORD', ' '.join(argv))
        self.assertIn('SELECT', ' '.join(argv))
        child_env = spy.call_args.kwargs['env']
        self.assertNotIn('CANO_BACKUP_KEY_HEX', child_env)
        self.assertEqual(child_env['PGPASSWORD'], 'PRIVATE-PASSWORD')

    def test_empty_render_database_is_rejected_before_dump(self):
        spy = Mock(return_value=self.row('research_library_persistent_db', [], False))
        with patch('cano_backup_source_gate.shutil.which', return_value='/bin/psql'):
            with self.assertRaisesRegex(ValueError, 'application source inventory'):
                require_application_source(self.env, 'full', expected_host=self.expected_host,
                                           expected_database='assistant_pg', runner=spy)

    def test_correct_name_wrong_schema_is_rejected(self):
        spy = Mock(return_value=self.row('assistant_pg', ['private_colony_snapshots'], True))
        with patch('cano_backup_source_gate.shutil.which', return_value='/bin/psql'):
            with self.assertRaisesRegex(ValueError, 'application source inventory'):
                require_application_source(self.env, 'full', expected_host=self.expected_host,
                                           expected_database='assistant_pg', runner=spy)

    def test_correct_schema_but_no_real_records_is_rejected(self):
        spy = Mock(return_value=self.row('assistant_pg', self.required, False))
        with patch('cano_backup_source_gate.shutil.which', return_value='/bin/psql'):
            with self.assertRaisesRegex(ValueError, 'application source inventory'):
                require_application_source(self.env, 'full', expected_host=self.expected_host,
                                           expected_database='assistant_pg', runner=spy)

    def test_missing_or_wrong_pin_aborts_without_child_process(self):
        spy = Mock()
        for host, db in [('', 'assistant_pg'), (self.expected_host, ''),
                         ('wrong.example.net', 'assistant_pg'),
                         (self.expected_host, 'wrong_db')]:
            with self.subTest(host=host, db=db):
                with self.assertRaises(ValueError):
                    require_application_source(self.env, 'full', expected_host=host,
                                               expected_database=db, runner=spy)
        spy.assert_not_called()

    def test_unrecognized_profile_and_invalid_identifiers_fail_closed(self):
        for profile in ('', 'all', 'unknown', 'full;DROP TABLE x'):
            with self.subTest(profile=profile):
                with self.assertRaises(ValueError):
                    require_application_source(self.env, profile,
                                               expected_host=self.expected_host,
                                               expected_database='assistant_pg', runner=Mock())
        with self.assertRaises(ValueError):
            require_application_source(self.env, 'full', expected_host=self.expected_host,
                                       expected_database='assistant_pg;DROP', runner=Mock())

    def test_psql_errors_do_not_expose_secret_or_internal_details(self):
        spy = Mock(side_effect=OSError('POSTGRESQL://PRIVATE-PASSWORD'))
        with patch('cano_backup_source_gate.shutil.which', return_value='/bin/psql'):
            with self.assertRaises(ValueError) as ctx:
                require_application_source(self.env, 'full', expected_host=self.expected_host,
                                           expected_database='assistant_pg', runner=spy)
        self.assertNotIn('PRIVATE-PASSWORD', str(ctx.exception))
        self.assertNotIn('POSTGRESQL://', str(ctx.exception))

    def test_profile_is_separate_for_colony_tasks_and_memory(self):
        self.assertEqual(len(APP_SOURCE_PROFILES['full']), 9)
        self.assertEqual(len(APP_SOURCE_PROFILES['colony']), 3)
        self.assertEqual(len(APP_SOURCE_PROFILES['tasks']), 5)
        self.assertEqual(len(APP_SOURCE_PROFILES['memory']), 1)
        self.assertEqual(set(APP_SOURCE_PROFILES['full']),
                         set().union(*(APP_SOURCE_PROFILES[x] for x in ('colony','tasks','memory'))))


if __name__=='__main__':
    unittest.main()
