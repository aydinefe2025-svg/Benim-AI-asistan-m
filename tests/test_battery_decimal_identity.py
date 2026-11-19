"""Regression for numerical text aliasing and independent battery holdout."""
import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'battery_curve_audit'))
import customer_preflight as product
from independent_holdout import create_manifest, verify_manifest


class DecimalIdentityTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.manifest = {'schema': product.SCHEMA, 'files': []}

    def add(self, cell, body, units=('h', 'V')):
        path = cell + '.csv'
        data = f'Timestamp_1 [{units[0]}],DC1 [{units[1]}]\n' + body
        (self.root / path).write_text(data, encoding='utf-8')
        self.manifest['files'].append({'path': path, 'cell': cell, 'mode': 'dchg'})

    def test_numeric_alias_detected_raw_hash_preserved(self):
        self.add('A', '0,3.4\n1,3.3\n2,3.2\n')
        self.add('B', '0.0,3.40\n1.00,3.30\n2e0,3.200\n')
        report = product.audit_customer(self.manifest, self.root)
        self.assertEqual(report['unique_curve_count'], 2)
        self.assertEqual(report['numeric_unique_curve_count'], 1)
        self.assertEqual(len(report['duplicate_groups']), 0)
        self.assertEqual(len(report['numeric_duplicate_groups']), 1)
        self.assertEqual(report['review_status'], 'REVIEW_REQUIRED')
        a, b = report['all_curve_identity']
        self.assertNotEqual(a['trace_sha256'], b['trace_sha256'])
        self.assertEqual(a['numeric_trace_sha256'], b['numeric_trace_sha256'])

    def test_not_rounding_close_values(self):
        self.add('A', '0,3.4\n1,3.3\n')
        self.add('B', '0.0,3.4000000000000000000000000001\n1,3.3\n')
        report = product.audit_customer(self.manifest, self.root)
        self.assertEqual(report['numeric_unique_curve_count'], 2)
        self.assertEqual(len(report['numeric_duplicate_groups']), 0)

    def test_exponent_and_trailing_zeros_normalize(self):
        self.assertEqual(product.canonical_numeric_token('1000.0'), product.canonical_numeric_token('1e3'))
        self.assertEqual(product.canonical_numeric_token('0.0001000'), product.canonical_numeric_token('1e-4'))
        self.assertEqual(product.canonical_numeric_token('-0.0'), '0')

    def test_bad_numeric_input_rejected(self):
        for val in ('nan', 'Inf', '-3', 'garbage'):
            with self.subTest(val=val), self.assertRaises(ValueError):
                product.canonical_numeric_token(val)

    def test_mixed_units_fail_before_alias_detection(self):
        self.add('A', '0,3.4\n1,3.3\n')
        self.add('B', '0.0,3.40\n1,3.30\n', units=('s', 'V'))
        with self.assertRaisesRegex(ValueError, 'mixed time/voltage units'):
            product.audit_customer(self.manifest, self.root)

    def test_raw_original_trace_hash_unchanged(self):
        self.add('A', '0,3.4\n1,3.3\n')
        report = product.audit_customer(self.manifest, self.root)
        self.assertEqual(report['all_curve_identity'][0]['trace_sha256'],
                         product.sha256(b'0\t3.4\n1\t3.3\n'))

    def test_valid_trailing_short_rows(self):
        self.add('A', '0,3.4,0,3.0\n1,3.3\n')
        (self.root / 'A.csv').write_text(
            'Timestamp_1 [h],DC1 [V],Timestamp_2 [h],DC2 [V]\n0,3.4,0,3.0\n1,3.3\n2,3.2,1,2.9\n',
            encoding='utf-8')
        report = product.audit_customer(self.manifest, self.root)
        self.assertEqual(report['measured_time_voltage_pairs'], 5)
        self.assertEqual(report['trace_count'], 2)

    def test_holdout_groups_decimal_alias_as_one_component(self):
        self.add('A', '0,3.4\n1,3.3\n2,3.2\n')
        self.add('B', '0.0,3.40\n1.00,3.30\n2e0,3.200\n')
        self.add('C', '0,3.7\n1,3.6\n2,3.5\n')
        self.add('D', '0,2.7\n1,2.6\n2,2.5\n')
        report = product.audit_customer(self.manifest, self.root)
        split = create_manifest(report)
        assignments = {x['cell']: x['partition'] for x in split['assignments']}
        self.assertEqual(assignments['A'], assignments['B'])
        self.assertEqual(split['independent_cell_group_count'], 3)
        self.assertEqual(len(set(assignments.values())), 3)
        verify_manifest(report, split)

    def test_partial_normalized_identity_fails_closed(self):
        self.add('A', '0,3.4\n1,3.3\n')
        report = product.audit_customer(self.manifest, self.root)
        del report['all_curve_identity'][0]['numeric_trace_sha256']
        with self.assertRaisesRegex(ValueError, 'partial/invalid numeric trace identity'):
            create_manifest(report)


if __name__ == '__main__':
    unittest.main()
