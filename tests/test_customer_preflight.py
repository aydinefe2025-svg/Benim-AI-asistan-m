"""Customer CSV preflight: synthetic fixture tests, no claims about paid deployments."""
import copy
import hashlib
import json
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research" / "battery_curve_audit"))
import customer_preflight as product

HEADER = 'Timestamp_1 [h],DC1 [V],Timestamp_2 [h],DC2 [V],Timestamp_3 [h],DC3 [V]\n'


def csv_data(*, duplicate=False):
    # Distinct source file bytes can contain exactly identical first traces.
    first = ('0,3.5,0,3.0,0,2.5\n1,3.4,1,2.9,1,2.4\n'
             '2,3.3,2,2.8\n3,3.2\n')
    return HEADER + first if duplicate else HEADER + (
        '0,3.9,0,3.0,0,2.5\n1,3.8,1,2.9,1,2.4\n'
        '2,3.7,2,2.8\n3,3.6\n')


class CustomerPilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'A.csv').write_text(csv_data(duplicate=True), encoding='utf-8')
        (self.root / 'B.csv').write_text(csv_data(duplicate=True), encoding='utf-8')
        (self.root / 'C.csv').write_text(csv_data(duplicate=False).replace('3.0','3.7').replace('2.5','2.2').replace('2.9','3.6').replace('2.4','2.1').replace('2.8','3.5'), encoding='utf-8')
        (self.root / 'D.csv').write_text(csv_data(duplicate=False).replace('3.9','4.1').replace('3.0','3.8').replace('2.5','2.8').replace('2.9','3.9').replace('2.4','2.7').replace('2.8','4.0'), encoding='utf-8')
        self.manifest = {'schema': 'cano.battery.customer-files.v1', 'files': [
            {'path': f'{c}.csv', 'cell': c, 'mode': 'dchg'} for c in 'ABCD'
        ]}

    def test_duplicate_across_cells_and_short_rows_kept(self):
        report = product.audit_customer(self.manifest, self.root)
        self.assertEqual(report['source_files'], 4)
        self.assertEqual(report['trace_count'], 12)
        self.assertEqual(report['width_counts']['2'], 4)
        self.assertEqual(report['width_counts']['4'], 4)
        self.assertEqual(report['width_counts']['6'], 8)
        self.assertEqual(report['measured_time_voltage_pairs'], 36)
        matches = [g for g in report['duplicate_groups'] if {r['cell'] for r in g} == {'A','B'}]
        self.assertGreaterEqual(len(matches), 1)
        self.assertTrue(all('time_voltage_values' not in x for x in report['all_curve_identity']))
        self.assertEqual(report['review_status'], 'REVIEW_REQUIRED')

    def test_split_groups_identical_cells_even_if_file_bytes_differ(self):
        (self.root / 'B.csv').write_text((self.root / 'B.csv').read_text() + '\n', encoding='utf-8')
        report = product.audit_customer(self.manifest, self.root)
        split = product.generate_holdout(report)
        a = {x['cell']: x['partition'] for x in split['assignments']}
        self.assertEqual(a['A'], a['B'])
        self.assertEqual(set(a.values()), {'train', 'validation', 'test'})
        self.assertEqual(split['independent_cell_group_count'], 3)

    def test_manifest_path_escape_and_symlink_blocked(self):
        bad = copy.deepcopy(self.manifest)
        bad['files'][0]['path'] = '../outside.csv'
        with self.assertRaisesRegex(ValueError, 'path'):
            product.audit_customer(bad, self.root)
        outside = self.root.parent / (self.root.name + '-outside.csv')
        outside.write_text(csv_data(), encoding='utf-8')
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        link = self.root / 'escape.csv'
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            return
        bad['files'][0]['path'] = 'escape.csv'
        with self.assertRaisesRegex(ValueError, 'path'):
            product.audit_customer(bad, self.root)

    def test_missing_voltage_is_not_filled_with_zero(self):
        (self.root / 'A.csv').write_text(HEADER + '0,3.5,0,3.1,0,2.5\n1,,1,3.0,1,2.4\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'pair'):
            product.audit_customer(self.manifest, self.root)

    def test_unordered_time_or_nonfinite_voltage_rejected(self):
        (self.root / 'A.csv').write_text(HEADER + '1,3.5,1,3.1,1,2.5\n0,3.4,2,3.0,2,2.4\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'time'):
            product.audit_customer(self.manifest, self.root)
        (self.root / 'A.csv').write_text(HEADER + '0,NaN,0,3.1,0,2.5\n1,3.4,1,3.0,1,2.4\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'finite'):
            product.audit_customer(self.manifest, self.root)

    def test_duplicate_file_paths_and_bad_schema_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad['files'].append({'path':'A.csv','cell':'E','mode':'dchg'})
        with self.assertRaisesRegex(ValueError, 'duplicate path'):
            product.audit_customer(bad, self.root)
        bad = copy.deepcopy(self.manifest)
        bad['schema'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'schema'):
            product.audit_customer(bad, self.root)

    def test_two_column_and_four_column_files_supported(self):
        (self.root / 'A.csv').write_text('Timestamp [h],Voltage [V]\n0,3.4\n1,3.3\n', encoding='utf-8')
        (self.root / 'B.csv').write_text('Timestamp 1,Voltage [V],Timestamp 2,Voltage [V]\n0,3.4,0,3.2\n1,3.3,1,3.1\n', encoding='utf-8')
        report = product.audit_customer(self.manifest, self.root)
        self.assertEqual(report['trace_count'], 9)
        self.assertEqual(report['width_counts']['2'], 4)  # 2 A rows, 1 C row, 1 D row

    def test_insufficient_independent_groups_blocks_holdout(self):
        bad = copy.deepcopy(self.manifest)
        bad['files'] = bad['files'][:2]
        report = product.audit_customer(bad, self.root)
        with self.assertRaisesRegex(ValueError, 'fewer than three'):
            product.generate_holdout(report)

if __name__ == '__main__':
    unittest.main(verbosity=2)
