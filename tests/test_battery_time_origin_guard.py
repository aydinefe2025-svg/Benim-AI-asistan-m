"""Behavioral regression: changed acquisition time origin cannot quietly clear clones.
Only synthetic time-voltage curves. Not a field ground truth assessment.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'/'battery_curve_audit'))
import customer_pipeline as app
import integrated_customer_gate as integrated


def csv_text(v0=4.0, time_shift=0.0, *, n=128, slope=0.7):
    body=['Timestamp_1 [h],DC1 [V]']
    for i in range(n):
        t=time_shift+i
        v=v0-slope*i/127 + 0.02*(i/127)*(1-i/127)
        body.append(f'{t:.8f},{v:.8f}')
    return '\n'.join(body)+'\n'

class TimeOriginSafetyTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.entries=[]

    def add(self,cell,voltage=4.0,time_shift=0.0, n=128,slope=0.7):
        (self.root/(cell+'.csv')).write_text(csv_text(voltage,time_shift,n=n,slope=slope))
        self.entries.append({'path':cell+'.csv','cell':cell,'mode':'dchg'})

    def evaluate(self):
        return app.audit_offline({'schema':'cano.battery.customer-files.v1','files':self.entries},self.root)

    def test_constant_time_origin_shift_cannot_appear_clean(self):
        self.add('A',4.0,0.0)
        self.add('B',4.0,3.0)
        self.add('C',3.6)
        self.add('D',3.2)
        report,private=self.evaluate()
        self.assertEqual(report['decision'],'REVIEW_REQUIRED')
        self.assertGreater(report['time_origin_near_candidates'],0)
        self.assertGreater(report['near_candidates'],0)
        self.assertEqual(private['by_cell']['A'],private['by_cell']['B'])
        groups=private['split']['groups']
        self.assertTrue(any(set(['A','B'])<=set(g['cells']) for g in groups))

    def test_independent_different_voltage_does_not_gain_false_origin_match(self):
        self.add('A',4.0,0.0)
        self.add('B',3.8,3.0)
        self.add('C',3.5)
        self.add('D',3.0)
        report,_=self.evaluate()
        self.assertEqual(report['decision'],'SCREEN_ONLY_NO_CROSS_CELL_CANDIDATES')
        self.assertEqual(report['time_origin_near_candidates'],0)

    def test_original_same_origin_duplicate_is_not_recounted(self):
        self.add('A',4.0)
        self.add('B',4.0)
        self.add('C',3.6)
        self.add('D',3.2)
        report,_=self.evaluate()
        self.assertEqual(report['decision'],'REVIEW_REQUIRED')
        self.assertEqual(report['time_origin_near_candidates'],0)
        self.assertGreater(report['cross_cell_numeric_duplicate_groups'],0)

    def test_time_warp_is_not_silently_equated_with_origin_shift(self):
        self.add('A',4.0)
        self.add('B',4.0,3.0,slope=0.9)
        self.add('C',3.6)
        self.add('D',3.2)
        report,_=self.evaluate()
        self.assertEqual(report['time_origin_near_candidates'],0)

    def test_integrated_acceptance_gate_also_refuses_shifted_origin(self):
        self.add('A',4.0,0.0)
        self.add('B',4.0,3.0)
        self.add('C',3.6)
        self.add('D',3.2)
        result=integrated.integrated_check(
            {'schema':'cano.battery.customer-files.v1','files':self.entries},self.root)
        self.assertEqual(result['decision'],'REVIEW_REQUIRED')
        self.assertGreater(result['relative_time_origin_candidate_count'],0)
        self.assertTrue(any({'A','B'} <= set(g['cells']) for g in result['split']['groups']))

    def test_short_shift_remains_unscreened_review_not_pseudocandidate(self):
        self.add('A',4.0)
        self.add('B',4.0,3.0,n=80)
        self.add('C',3.6)
        self.add('D',3.2)
        report,_=self.evaluate()
        self.assertEqual(report['decision'],'REVIEW_REQUIRED')
        self.assertEqual(report['time_origin_near_candidates'],0)
        self.assertGreater(report['unscreened_traces'],0)

if __name__=='__main__':unittest.main()
