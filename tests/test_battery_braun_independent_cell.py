"""Synthetic safety contract tests; physical-cell source runs separately in CI."""
import hashlib
from unittest.mock import patch
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"research"/"battery_curve_audit"))
import braun_independent_cell_audit as b

def sample(delta=0.,n=4096):
    rows=["Time,Current,Voltage,Temperature"]
    for i in range(n):
        rows.append(f"{i},{1.1},{3.0+delta+i*0.00005:.9f},{24.5}")
    return ('\n'.join(rows)+'\n').encode()

class BraunTwoPhysicalCellsAudit(unittest.TestCase):
    def test_exact_four_physical_axes_and_measured_time(self):
        t,v,meta=b.parse_window(sample())
        self.assertEqual((len(t),t[0],t[-1]),(4096,0,4095))
        self.assertAlmostEqual(v[0],3.0)
        self.assertEqual(meta['rows_in_window'],4096)

    def test_soc_instead_of_time_and_wrong_header_rejected(self):
        for text in ("SOC,Current,Voltage,Temperature", "Voltage,Current,Time,Temperature"):
            with self.subTest(text=text),self.assertRaises(ValueError):
                b.parse_window(sample().replace(b'Time,Current,Voltage,Temperature',text.encode(),1))

    def test_missing_nonfinite_or_backward_time_rejected(self):
        for text in (sample().replace(b'3.000000000',b'nan',1),sample().replace(b'1,1.1',b'0,1.1',1),sample()[:300]):
            with self.subTest(raw=text[:40]),self.assertRaises(ValueError):
                b.parse_window(text)

    def test_source_authentication_blocks_modified_even_valid_csv(self):
        aged,fresh=sample(.08),sample(0)
        with patch.dict(b.SOURCE,{'aged':('a.csv',hashlib.md5(aged).hexdigest()),'fresh':('f.csv',hashlib.md5(fresh).hexdigest())},clear=True):
            with self.assertRaisesRegex(ValueError,'MD5'):
                b.audit_sources({'aged':aged,'fresh':fresh+b'\n'})

    def test_two_different_physical_ids_and_controlled_curve_probe(self):
        aged,fresh=sample(.08),sample(0)
        with patch.dict(b.SOURCE,{'aged':('a.csv',hashlib.md5(aged).hexdigest()),'fresh':('f.csv',hashlib.md5(fresh).hexdigest())},clear=True):
            report=b.audit_sources({'aged':aged,'fresh':fresh})
        self.assertEqual(report['decision'],'SCREEN_ONLY_NOT_CERTIFIED')
        self.assertTrue(report['original_publisher_md5_verified'])
        self.assertEqual(report['original_cell_classes'],['fresh','pre-aged'])
        self.assertTrue(report['two_distinct_source_files'])
        for cell in ('aged','fresh'):
            self.assertEqual(report['sources'][cell]['max_abs_diff_mv'],1)
            self.assertFalse(report['sources'][cell]['controlled_10mv_detected'])

    def test_required_two_source_ids(self):
        with self.assertRaises(ValueError):
            b.audit_sources({'fresh':sample()})

if __name__=='__main__':unittest.main()