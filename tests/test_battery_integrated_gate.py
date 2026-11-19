"""Synthetic integration tests; not new measurements or customer validation."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'battery_curve_audit'))
import customer_preflight
import numeric_equivalence_guard
import integrated_customer_gate as gate


def curve(cell, fmt='clean', tiny=0., count=121, units=('h','V')):
    head=f'Timestamp_1 [{units[0]}],DC1 [{units[1]}]\n'
    lines=[]
    for i in range(count):
        val=4.3 - i*.004 + tiny
        if fmt == 'fixed3':
            lines.append(f'{i},{val:.3f}')
        elif fmt == 'fixed4':
            lines.append(f'{i}.0000,{val:.4f}')
        else:
            lines.append(f'{i},{val:.6f}')
    return head+'\n'.join(lines)+'\n'

class IntegratedGateTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root=Path(d.name)
        self.manifest={'schema':'cano.battery.customer-files.v1','files':[]}
    def add(self, name, data, mode='dchg'):
        (self.root/f'{name}.csv').write_text(data,encoding='utf-8')
        self.manifest['files'].append({'path':f'{name}.csv','cell':name,'mode':mode})
    def setup_distinct(self):
        for i,c in enumerate('ABCD'):
            self.add(c,curve(c,tiny=i*0.10))
    def test_distinct_full_length_can_issue_screen_only_split(self):
        self.setup_distinct()
        result=gate.integrated_check(self.manifest,self.root)
        self.assertEqual(result['decision'],'PASS_SCREEN_ONLY')
        self.assertEqual(result['numeric_unique'],4)
        self.assertEqual(result['near_candidate_count'],0)
        self.assertEqual(result['unscreened_trace_count'],0)
        self.assertEqual(result['split']['exact_and_candidate_connected_groups'],4)
        self.assertEqual(sum(result['split']['partition_cell_counts'].values()),4)
        self.assertTrue(gate.verify_report(self.manifest,self.root,result))
    def test_different_text_identical_decimal_blocks_unreviewed_acceptance(self):
        self.add('A',curve('A',fmt='fixed3'))
        self.add('B',curve('B',fmt='fixed4'))
        self.add('C',curve('C',tiny=.2))
        self.add('D',curve('D',tiny=.4))
        report=gate.integrated_check(self.manifest,self.root)
        self.assertEqual(report['decision'],'REVIEW_REQUIRED')
        self.assertGreaterEqual(report['numeric_only_duplicate_groups'],1)
        self.assertEqual(report['near_candidate_count'],0)
        assignments={a['cell']:a['partition'] for a in report['split']['assignments']}
        self.assertEqual(assignments['A'],assignments['B'])
        self.assertNotEqual(report['raw_unique'],report['numeric_unique'])
    def test_interpolated_near_curve_requires_review_and_stays_in_same_group(self):
        self.add('A',curve('A'))
        self.add('B',curve('B',tiny=.0007))
        self.add('C',curve('C',tiny=.25))
        self.add('D',curve('D',tiny=.50))
        report=gate.integrated_check(self.manifest,self.root)
        self.assertEqual(report['near_candidate_count'],1)
        self.assertEqual(report['decision'],'REVIEW_REQUIRED')
        groups={a['cell']:a['partition'] for a in report['split']['assignments']}
        self.assertEqual(groups['A'],groups['B'])
    def test_short_trace_is_unscreened_and_never_accepted(self):
        self.setup_distinct()
        (self.root/'A.csv').write_text(curve('A',count=2),encoding='utf-8')
        report=gate.integrated_check(self.manifest,self.root)
        self.assertEqual(report['decision'],'REVIEW_REQUIRED')
        self.assertEqual(report['unscreened_trace_count'],1)
    def test_unit_mismatch_blocks_before_all_duplicate_comparisons(self):
        self.setup_distinct()
        (self.root/'B.csv').write_text(curve('B',units=('s','V')),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'UNIT_REVIEW_REQUIRED'):
            gate.integrated_check(self.manifest,self.root)
    def test_different_source_after_numeric_audit_is_rejected(self):
        self.setup_distinct()
        numeric=numeric_equivalence_guard.build_numeric_audit(self.manifest,self.root)
        (self.root/'A.csv').write_text(curve('A',tiny=.1),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'source changed'):
            gate.screen_numeric_report(numeric,self.manifest,self.root)
    def test_tampered_split_is_not_accepted_by_reverification(self):
        self.setup_distinct()
        report=gate.integrated_check(self.manifest,self.root)
        report['split']['assignments'][0]['partition']='other'
        with self.assertRaisesRegex(ValueError,'(mismatch|altered|partition)'):
            gate.verify_report(self.manifest,self.root,report)
    def test_millivolts_and_seconds_use_physical_2mv_near_threshold(self):
        for j, name in enumerate('ABCD'):
            offset = [0, .7, 150, 300][j]
            rows = [f'{i},{4200 - 4*i + offset:.3f}' for i in range(121)]
            self.add(name, 'Timestamp_1 [s],DC1 [mV]\n' + '\n'.join(rows) + '\n')
        report = gate.integrated_check(self.manifest, self.root)
        self.assertEqual(report['unit_contract']['time_unit'], 's')
        self.assertEqual(report['unit_contract']['voltage_unit'], 'mv')
        self.assertEqual(report['near_candidate_count'], 1)
        self.assertEqual(report['decision'], 'REVIEW_REQUIRED')

    def test_flat_trace_is_unscreened(self):
        self.setup_distinct()
        (self.root/'A.csv').write_text(
            'Timestamp_1 [h],DC1 [V]\n' + '\n'.join(f'{i},3.000' for i in range(121))+'\n',
            encoding='utf-8')
        report=gate.integrated_check(self.manifest,self.root)
        self.assertEqual(report['decision'],'REVIEW_REQUIRED')
        self.assertEqual(report['unscreened_traces'][0]['reason'],'flat_trace')

    def test_cli_cannot_leave_stale_accepted_split_on_review(self):
        self.add('A',curve('A'))
        self.add('B',curve('B',tiny=.0007))
        self.add('C',curve('C',tiny=.25))
        self.add('D',curve('D',tiny=.50))
        manifest_file=self.root/'manifest.json'
        manifest_file.write_text(json.dumps(self.manifest),encoding='utf-8')
        accepted=self.root/'accepted.json'
        accepted.write_text('old stale accepted split',encoding='utf-8')
        proc=subprocess.run([sys.executable, str(Path(gate.__file__)), '--manifest',str(manifest_file),
            '--root',str(self.root),'--report',str(self.root/'combined.json'),
            '--accepted-split',str(accepted)],capture_output=True,text=True)
        self.assertEqual(proc.returncode,2)
        self.assertFalse(accepted.exists())
        report=json.loads((self.root/'combined.json').read_text())
        self.assertEqual(report['decision'],'REVIEW_REQUIRED')

    def test_old_exact_only_cli_cannot_write_accepted_split(self):
        self.setup_distinct()
        manifest_file = self.root/'manifest.json'
        manifest_file.write_text(json.dumps(self.manifest), encoding='utf-8')
        accepted_file = self.root/'legacy_accepted.json'
        proc = subprocess.run([sys.executable, str(Path(customer_preflight.__file__)),
            '--manifest',str(manifest_file), '--root',str(self.root),
            '--report',str(self.root/'audit.json'), '--split',str(accepted_file)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode,2,proc.stdout+proc.stderr)
        self.assertFalse(accepted_file.exists())

    def test_insufficient_groups_fail_closed(self):
        for i,c in enumerate('AB'):
            self.add(c,curve(c,tiny=i*.2))
        report=gate.integrated_check(self.manifest,self.root)
        self.assertEqual(report['decision'],'BLOCK_INSUFFICIENT_GROUPS')
        self.assertIsNone(report['split'])

if __name__=='__main__':
    unittest.main(verbosity=2)
