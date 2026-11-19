"""Synthetic regression: physical unit mismatches must block customer duplicate checks."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'battery_curve_audit'))
import customer_preflight as product


class UnitContractTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.manifest = {'schema': product.SCHEMA, 'files': []}

    def add(self, filename, content, cell):
        (self.root / filename).write_text(content, encoding='utf-8')
        self.manifest['files'].append({'path': filename, 'cell': cell, 'mode': 'dchg'})

    @staticmethod
    def csv(t='h', v='V'):
        return f'Timestamp_1 [{t}],DC1 [{v}]\n0,3.4\n1,3.3\n'

    def test_time_units_mismatch_rejected_before_duplicate_check(self):
        self.add('a.csv', self.csv('h'), 'A')
        self.add('b.csv', self.csv('s'), 'B')
        with self.assertRaisesRegex(ValueError, 'mixed time/voltage units'):
            product.audit_customer(self.manifest, self.root)

    def test_voltage_units_mismatch_rejected_before_duplicate_check(self):
        self.add('a.csv', self.csv('h', 'V'), 'A')
        self.add('b.csv', self.csv('h', 'mV'), 'B')
        with self.assertRaisesRegex(ValueError, 'mixed time/voltage units'):
            product.audit_customer(self.manifest, self.root)

    def test_missing_units_rejected(self):
        self.add('a.csv', 'Timestamp_1,DC1 [V]\n0,3.4\n1,3.3\n', 'A')
        with self.assertRaisesRegex(ValueError, 'missing/unknown units'):
            product.audit_customer(self.manifest, self.root)

    def test_intra_file_mismatch_rejected(self):
        self.add('a.csv', 'Timestamp_1 [h],DC1 [V],Timestamp_2 [s],DC2 [V]\n0,3.4,0,3.4\n1,3.3,1,3.3\n', 'A')
        with self.assertRaisesRegex(ValueError, 'mixed units in file'):
            product.audit_customer(self.manifest, self.root)

    def test_unsupported_unit_rejected(self):
        self.add('a.csv', self.csv('minute'), 'A')
        with self.assertRaisesRegex(ValueError, 'missing/unknown units'):
            product.audit_customer(self.manifest, self.root)

    def test_same_units_report_still_works(self):
        self.add('a.csv', self.csv(), 'A')
        self.add('b.csv', self.csv(), 'B')
        report = product.audit_customer(self.manifest, self.root)
        self.assertEqual(report['unit_contract']['time_unit'], 'h')
        self.assertEqual(report['unit_contract']['voltage_unit'], 'v')
        self.assertEqual(report['review_status'], 'REVIEW_REQUIRED')
        self.assertEqual(len(report['duplicate_groups']), 1)

    def test_uniform_seconds_and_millivolts_accepted(self):
        self.add('a.csv', self.csv('s', 'mV'), 'A')
        report = product.audit_customer(self.manifest, self.root)
        self.assertEqual(report['unit_contract']['time_unit'], 's')
        self.assertEqual(report['unit_contract']['voltage_unit'], 'mv')

    def test_short_trailing_pair_stays_valid(self):
        self.add('a.csv', 'Timestamp_1 [h],DC1 [V],Timestamp_2 [h],DC2 [V]\n0,3.4,0,3.6\n1,3.3,1,3.5\n2,3.2\n', 'A')
        report = product.audit_customer(self.manifest, self.root)
        self.assertEqual(report['measured_time_voltage_pairs'], 5)
        self.assertEqual(report['width_counts']['2'], 1)


if __name__ == '__main__':
    unittest.main()
