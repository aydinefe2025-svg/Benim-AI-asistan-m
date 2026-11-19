"""End-to-end synthetic customer files; never real customer measurements."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'battery_curve_audit'))
import customer_pipeline as pipeline


def csv_curve(level='4.00', offset='0', unit='V', variant='normal', time_shift='0'):
    rows = [f'Timestamp_1 [h],DC1 [{unit}]']
    for i in range(120):
        t = Decimal(i) + Decimal(time_shift)
        v = Decimal(level) - Decimal(i) * Decimal('0.002') + Decimal(offset)
        if unit == 'mV':
            v *= 1000
        if variant == 'expanded':
            rows.append(f'{t:.1f},{v:.4f}')
        else:
            rows.append(f'{t},{v}')
    return '\n'.join(rows) + '\n'


class CustomerOneCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def setup_files(self, specs):
        items = []
        for cell, options in specs:
            p = self.root / (cell + '.csv')
            p.write_text(csv_curve(**options), encoding='utf-8')
            items.append({'path': p.name, 'cell': cell, 'mode': 'dchg'})
        return {'schema': 'cano.battery.customer-files.v1', 'files': items}

    def test_numeric_equivalent_different_text_stays_atomic(self):
        manifest = self.setup_files([
            ('A', {'level': '4.0'}), ('B', {'level':'4.0','variant':'expanded'}),
            ('C', {'level':'3.6'}), ('D', {'level':'3.2'})])
        summary, private = pipeline.audit_offline(manifest, self.root)
        self.assertEqual(summary['numeric_only_duplicate_groups'], 1)
        self.assertEqual(summary['near_candidates'], 0)
        self.assertEqual(summary['independent_groups'], 3)
        self.assertEqual(summary['decision'], 'REVIEW_REQUIRED')
        self.assertEqual(private['by_cell']['A'], private['by_cell']['B'])
        self.assertEqual(set(private['by_cell'].values()), {'train', 'validation', 'test'})

    def test_near_candidate_connects_cells_and_blocks_customer_release(self):
        manifest = self.setup_files([
            ('A', {'level': '4.0'}), ('B', {'level':'4.0','variant':'expanded'}),
            ('C', {'level':'3.6'}), ('D', {'level':'3.6','offset':'0.001'}),
            ('E', {'level':'3.2'})])
        summary, private = pipeline.audit_offline(manifest, self.root)
        self.assertEqual(summary['near_candidates'], 1)
        self.assertEqual(summary['independent_groups'], 3)
        self.assertEqual(summary['decision'], 'REVIEW_REQUIRED')
        self.assertEqual(private['by_cell']['C'], private['by_cell']['D'])
        self.assertNotEqual(private['by_cell']['C'], private['by_cell']['E'])

    def test_near_matches_use_millivolts_as_volts(self):
        manifest = self.setup_files([
            ('A', {'level':'4.0', 'unit':'mV'}),
            ('B', {'level':'4.0', 'offset':'0.001', 'unit':'mV'}),
            ('C', {'level':'3.2', 'unit':'mV'}),
            ('D', {'level':'2.7', 'unit':'mV'})])
        summary, private = pipeline.audit_offline(manifest, self.root)
        self.assertEqual(summary['near_candidates'], 1)
        self.assertEqual(summary['unit_contract']['voltage_unit'], 'mv')
        self.assertEqual(private['by_cell']['A'], private['by_cell']['B'])

    def test_mixed_units_fail_closed(self):
        manifest = self.setup_files([
            ('A', {'level':'4.0','unit':'V'}),
            ('B', {'level':'4.0','unit':'mV'}),
            ('C', {'level':'3.2','unit':'V'})])
        with self.assertRaisesRegex(ValueError, 'UNIT_REVIEW_REQUIRED'):
            pipeline.audit_offline(manifest, self.root)

    def test_fewer_than_three_groups_block_release(self):
        manifest = self.setup_files([('A', {'level':'4.0'}), ('B', {'level':'4.0','variant':'expanded'}), ('C', {'level':'3.6'})])
        summary, private = pipeline.audit_offline(manifest, self.root)
        self.assertEqual(summary['decision'], 'BLOCK_INSUFFICIENT_GROUPS')
        self.assertIsNone(private)

    def test_public_summary_never_exposes_customer_identifiers_or_raw_data(self):
        manifest = self.setup_files([('secret_A', {'level':'4.0'}), ('secret_B', {'level':'3.6'}), ('secret_C', {'level':'3.2'})])
        summary, private = pipeline.audit_offline(manifest, self.root)
        out = self.root / 'public.json'
        pipeline.save_reports(summary, private, out)
        visible = out.read_text()
        self.assertNotIn('secret_', visible)
        self.assertNotIn('.csv', visible)
        self.assertNotIn('trace_sha256', visible)
        self.assertNotIn('source_sha256', visible)
        self.assertNotIn('4.0000', visible)
        self.assertEqual(summary['decision'], 'SCREEN_ONLY_NO_CROSS_CELL_CANDIDATES')
        self.assertEqual(summary['source_files'], 3)
        self.assertEqual(summary['sample_pairs'], 360)
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)

    def test_private_split_requires_explicit_output_and_is_labelled_unapproved(self):
        manifest = self.setup_files([('A', {'level':'4.0'}), ('B', {'level':'3.6'}), ('C', {'level':'3.2'})])
        summary, private = pipeline.audit_offline(manifest, self.root)
        out = self.root / 'summary.json'
        privileged = self.root / 'private.json'
        pipeline.save_reports(summary, private, out, privileged)
        private_json = json.loads(privileged.read_text())
        self.assertEqual(private_json['status'], 'NOT_CERTIFIED')
        self.assertEqual({c['cell'] for c in private_json['split']['assignments']}, {'A','B','C'})
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(privileged.stat().st_mode), 0o600)

    def test_never_overwrite_existing_report_or_source_csv(self):
        manifest = self.setup_files([('A', {'level':'4.0'}), ('B', {'level':'3.6'}), ('C', {'level':'3.2'})])
        summary, private = pipeline.audit_offline(manifest, self.root)
        out = self.root / 'output.json'
        out.write_text('SENTINEL')
        with self.assertRaisesRegex(ValueError, 'existing|exists'):
            pipeline.save_reports(summary, private, out)
        self.assertEqual(out.read_text(), 'SENTINEL')
        original = self.root / 'A.csv'
        source_data = original.read_bytes()
        with self.assertRaises(ValueError):
            pipeline.save_reports(summary, private, original, source_paths=[original])
        self.assertEqual(original.read_bytes(), source_data)

    def test_short_charge_rows_are_retained_without_invented_zeros(self):
        header = 'Timestamp_1 [h],DC1 [V],Timestamp_2 [h],DC2 [V],Timestamp_3 [h],DC3 [V]\n'
        files = []
        for cell, level in (('A', '4.0'), ('B', '3.5'), ('C', '3.0')):
            rows = []
            for i in range(120):
                v = Decimal(level) - Decimal(i)*Decimal('0.002')
                row = f'{i},{v},{i},{v-Decimal("0.1")},{i},{v-Decimal("0.2")}'
                if i >= 117:
                    row = f'{i},{v}'
                rows.append(row)
            (self.root / (cell+'.csv')).write_text(header+'\n'.join(rows)+'\n')
            files.append({'path': cell+'.csv', 'cell': cell, 'mode': 'chg'})
        manifest = {'schema':'cano.battery.customer-files.v1','files':files}
        summary, private = pipeline.audit_offline(manifest, self.root)
        self.assertEqual(summary['trace_count'], 9)
        self.assertEqual(summary['sample_pairs'], 3*(120+117+117))
        self.assertTrue(summary['holdout_possible'])

    def test_command_line_fails_closed_on_review_but_writes_safe_summary(self):
        manifest = self.setup_files([
            ('A', {'level':'4.0'}), ('B', {'level':'4.0','variant':'expanded'}),
            ('C', {'level':'3.6'}), ('D', {'level':'3.2'})])
        mp = self.root / 'manifest.json'
        mp.write_text(json.dumps(manifest))
        public = self.root / 'public.json'
        code = pipeline.main(['--manifest', str(mp), '--root', str(self.root), '--summary', str(public)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(public.read_text())['decision'], 'REVIEW_REQUIRED')
        self.assertNotIn('A.csv', public.read_text())
        explicit = self.root / 'read-only.json'
        code = pipeline.main(['--manifest', str(mp), '--root', str(self.root),
                              '--summary', str(explicit), '--report-only'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(explicit.read_text())['decision'], 'REVIEW_REQUIRED')

    def test_command_line_never_overwrites_manifest(self):
        manifest = self.setup_files([('A', {'level':'4.0'}), ('B', {'level':'3.6'}), ('C', {'level':'3.2'})])
        mp = self.root/'manifest.json'
        mp.write_text(json.dumps(manifest))
        original = mp.read_bytes()
        code = pipeline.main(['--manifest',str(mp),'--root',str(self.root),'--summary',str(mp)])
        self.assertEqual(code, 2)
        self.assertEqual(mp.read_bytes(), original)

    def test_too_many_traces_rejected_before_near_quadratic_work(self):
        manifest = self.setup_files([('A', {'level':'4.0'}), ('B', {'level':'3.6'}), ('C', {'level':'3.2'})])
        with self.assertRaisesRegex(ValueError, 'trace budget'):
            pipeline.audit_offline(manifest, self.root, max_traces=2)


if __name__ == '__main__':
    unittest.main()
