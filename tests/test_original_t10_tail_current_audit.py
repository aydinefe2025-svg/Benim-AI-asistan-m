"""Synthetic shape/identity guards; real Figshare source is separately replayed in CI."""
from __future__ import annotations
import io
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from research.battery_curve_audit.original_t10_tail_current_audit import (
    integrate_discharge, audit, verify_original_zip,
)
NAME='TP_k01_04_01_ET_T10.csv'

def zipped(rows, head='run_time,c_cur,c_vol,step_type'):
    buff=io.BytesIO()
    with ZipFile(buff,'w',compression=ZIP_DEFLATED) as z:
        z.writestr(NAME,head+'\n'+''.join(','.join(map(str,row))+'\n' for row in rows))
    return buff.getvalue()

def series():
    return [(str(n), '-2', '2.5', '22') for n in range(60)] + [('60','0','2.5','23')]

class TestOriginalT10CurrentTaper(unittest.TestCase):
    def test_known_right_endpoint_coulometry_with_current_categories(self):
        b=zipped(series())
        with ZipFile(io.BytesIO(b)) as z:
            result=integrate_discharge(z,NAME)
        self.assertEqual(result['discharge_rows'],60)
        self.assertAlmostEqual(result['capacity_mAh'],59*2/3.6,places=7)
        self.assertEqual(result['bin_capacity_mAh']['below_1A'],0)
        self.assertAlmostEqual(result['bin_duration_s']['1_to_4A'],59)
        self.assertEqual(result['bin_near_2p5V_fraction']['1_to_4A'],1)
    def test_reject_nonfinite_measurement(self):
        rows=series();rows[21]=(rows[21][0],'-2','nan','22')
        with ZipFile(io.BytesIO(zipped(rows))) as z:
            with self.assertRaisesRegex(ValueError,'nonfinite'):
                integrate_discharge(z,NAME)
    def test_reject_backward_timestamp(self):
        rows=series();rows[20]=('18.9','-2','2.5','22')
        with ZipFile(io.BytesIO(zipped(rows))) as z:
            with self.assertRaisesRegex(ValueError,'backwards'):
                integrate_discharge(z,NAME)
    def test_reject_missing_source_current_column(self):
        with ZipFile(io.BytesIO(zipped(series(),'run_time,not_current,c_vol,step_type'))) as z:
            with self.assertRaisesRegex(ValueError,'fields'):
                integrate_discharge(z,NAME)
    def test_reject_split_discharge_with_other_step(self):
        rows=series();rows[25]=('25','0','2.5','23');rows[26]=('26','-2','2.5','22')
        with ZipFile(io.BytesIO(zipped(rows))) as z:
            with self.assertRaisesRegex(ValueError,'more than one'):
                integrate_discharge(z,NAME)
    def test_reject_unsafe_zip_name(self):
        b=io.BytesIO()
        with ZipFile(b,'w') as z:z.writestr('../x.csv','rawdata')
        with self.assertRaisesRegex(ValueError,'unsafe'):
            verify_original_zip(b.getvalue())
    def test_reject_incomplete_original_set(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'unexpected.zip').write_bytes(b'no')
            with self.assertRaisesRegex(ValueError,'set missing'):
                audit(Path(d))

if __name__=='__main__':unittest.main()