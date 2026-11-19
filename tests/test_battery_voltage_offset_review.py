"""Synthetic-only regression for unresolved constant voltage-offset ambiguity."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'battery_curve_audit'))
import customer_pipeline
import near_duplicate_guard as near


def waveform(base=4.05, offset=0.0, phase=0.0, n=128):
    from math import sin, pi
    return [(float(i), base - 0.005*i + 0.018*sin(i/127*4*pi+phase) + offset) for i in range(n)]


def trace(cell, data, mode='dchg'):
    return {'cell':cell,'mode':mode,'run':1,'n':len(data),
            'times':[t for t,_ in data],'volts':[v for _,v in data],
            'trace_sha256':(cell.lower()*64)[:64]}


class OffsetAmbiguityTests(unittest.TestCase):
    def test_offset_clone_must_not_get_screen_only_clearance(self):
        a=waveform(); b=waveform(offset=.0035)
        physical=[trace('A',a),trace('B',b),trace('C',waveform(base=3.6)),trace('D',waveform(base=3.2))]
        self.assertFalse(near.candidates_for(physical))
        # Explicit review-only, NOT positive proof of physical copying.
        result=near.voltage_offset_review_candidates(physical)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['classification'],'VOLTAGE_OFFSET_AMBIGUOUS_REVIEW_ONLY')
        self.assertAlmostEqual(result[0]['voltage_offset_mv'],3.5,places=2)

    def test_offset_ambiguity_identical_observables_for_different_origin(self):
        # A stored measurement cannot encode whether it was transformed from a
        # known cell or independently recorded with the same voltage offset.
        clone=waveform(offset=.0035)
        independent=waveform(offset=.0035)
        self.assertEqual(clone,independent)
        x=trace('A',waveform()); y=trace('B',clone)
        z=trace('B',independent)
        self.assertEqual(near.voltage_offset_review_candidates([x,y]),
                         near.voltage_offset_review_candidates([x,z]))

    def test_large_offset_and_shape_changed_not_auto_labeled(self):
        a=trace('A',waveform())
        b=trace('B',waveform(offset=.03))
        c=trace('C',waveform(base=3.95,phase=.9))
        self.assertEqual(near.voltage_offset_review_candidates([a,b,c]),[])

    def test_mode_and_cell_safety(self):
        a=trace('A',waveform())
        b=trace('A',waveform(offset=.0035))
        c=trace('B',waveform(offset=.0035),mode='chg')
        self.assertEqual(near.voltage_offset_review_candidates([a,b,c]),[])

    def test_customer_holdout_is_review_required_for_offset_ambiguous_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            files=[]
            for cell, data in [ ('A',waveform()),('B',waveform(offset=.0035)),
                                ('C',waveform(base=3.6)),('D',waveform(base=3.2))]:
                (root/(cell+'.csv')).write_text('Timestamp_1 [h],DC1 [V]\n'+
                    ''.join(f'{int(t)},{v:.9f}\n' for t,v in data))
                files.append({'path':cell+'.csv','cell':cell,'mode':'dchg'})
            manifest={'schema':'cano.battery.customer-files.v1','files':files}
            summary,private=customer_pipeline.audit_offline(manifest,root)
            self.assertEqual(summary['decision'],'REVIEW_REQUIRED')
            self.assertEqual(summary['voltage_offset_ambiguous_candidates'],1)
            self.assertEqual(private['by_cell']['A'],private['by_cell']['B'])

if __name__ == '__main__': unittest.main()
