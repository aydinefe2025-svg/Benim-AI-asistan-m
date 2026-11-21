"""Fail-closed synthetic regression tests for the *source-method*, not real physics proof."""
import io
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from research.battery_curve_audit.cccv_protocol_split import (
    split_measured_discharge,audit,C20_A,
)

NAME='TP_k01_04_01_ET_T10.csv'

def source_rows():
    vals=[]
    vals.append(['0','4.100000','-0.04','22'])
    for n in range(1,41):
        v=2.51 if n==40 else 4.1-1.58*n/40
        vals.append([str(10*n),str(v),'-4.9','22'])
    for n in range(41,81):
        i=4.8-(4.8-.245)*(n-41)/39
        vals.append([str(10*n),'2.500',str(-i),'22'])
    vals.append(['810','2.5','0','23'])
    return vals

def ziprows(rows=None,headers='run_time,c_vol,c_cur,step_type'):
    buff=io.BytesIO()
    with ZipFile(buff,'w',compression=ZIP_DEFLATED) as z:
        z.writestr(NAME,headers+'\n'+''.join(','.join(map(str,x))+'\n' for x in (source_rows() if rows is None else rows)))
    return buff.getvalue()

class OriginalCCCVProtocolTests(unittest.TestCase):
    def measure(self,rows=None,headers='run_time,c_vol,c_cur,step_type'):
        with ZipFile(io.BytesIO(ziprows(rows,headers))) as z:
            return split_measured_discharge(z,NAME)
    def test_source_cccv_switch_and_term_c20(self):
        v=self.measure()
        self.assertEqual(v['discharge_rows'],81)
        self.assertAlmostEqual(v['terminal_current_A'],C20_A)
        a=v['boundaries']['2.505']
        self.assertAlmostEqual(a['CC_duration_s']+a['CV_duration_s'],800)
        self.assertAlmostEqual(a['CC_capacity_mAh']+a['CV_capacity_mAh'],v['full_discharge_capacity_mAh'],places=6)
        self.assertGreater(a['CV_near_2p5V_fraction'],.98)
    def test_threshold_shift_is_one_large_physical_sample(self):
        v=self.measure()['boundaries']
        self.assertEqual(v['2.505']['switch_time_s_from_phase_start'],410)
        self.assertEqual(v['2.510']['switch_time_s_from_phase_start'],400)
        self.assertAlmostEqual(v['2.505']['CC_capacity_mAh']-v['2.510']['CC_capacity_mAh'],4.9*10/3.6,places=5)
        self.assertAlmostEqual(v['2.505']['switch_source_cadence_s'],10)
    def test_startup_low_current_not_false_cv_trigger(self):
        a=self.measure()['boundaries']['current_taper_4p75A']
        self.assertGreater(a['switch_time_s_from_phase_start'],400)
    def test_reject_missing_C20_termination(self):
        rows=source_rows();rows[-2][2]='-0.9'
        with self.assertRaisesRegex(ValueError,'C/20'):
            self.measure(rows)
    def test_reject_missing_nominal_1C_plateau(self):
        rows=source_rows()
        for row in rows:
            if row[3]=='22' and abs(float(row[2]))>4:
                row[2]='-1.0'
        with self.assertRaisesRegex(ValueError,'1C'):
            self.measure(rows)
    def test_reject_missing_voltage_hold(self):
        rows=source_rows()
        for row in rows:
            row[1]='2.55'
        with self.assertRaisesRegex(ValueError,'1C|transition|C/20'):
            self.measure(rows)
    def test_reject_backward_timestamp(self):
        rows=source_rows();rows[5][0]='-1'
        with self.assertRaisesRegex(ValueError,'invalid source sample|backwards'):
            self.measure(rows)
    def test_reject_second_discharge_segment(self):
        rows=source_rows();rows[-1]=['810','2.5','0','23'];rows.append(['820','2.5','-0.245','22'])
        with self.assertRaisesRegex(ValueError,'multiple'):
            self.measure(rows)
    def test_reject_missing_voltage_column(self):
        with self.assertRaisesRegex(ValueError,'columns'):
            self.measure(headers='run_time,no_voltage,c_cur,step_type')
    def test_reject_unpinned_archive_set(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'untrusted.zip').write_bytes(b'x')
            with self.assertRaisesRegex(ValueError,'set missing'):
                audit(Path(d))

if __name__=='__main__':unittest.main()