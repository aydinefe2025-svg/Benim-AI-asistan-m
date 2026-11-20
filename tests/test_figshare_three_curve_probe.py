"""Finite and time-bound synthetic tests for *real-source* three-cell window reader."""
from hashlib import sha256
import io
import unittest
from zipfile import ZipFile
from research.battery_curve_audit.figshare_three_curve_probe import read_matched_window,compare_windows

NAME='TP_k01_05_01_ET_T23.csv'

def source(rows=1100,shift='0.0',reverse=False,withmeta=True):
    f=io.BytesIO()
    with ZipFile(f,'w') as z:
        lines=['run_time,c_vol,c_cur,step_type']
        for i in range(rows):
            t=rows-i if reverse else i
            lines.append(f'{t},{4.2-i*0.00001+float(shift):.6f},-0.1,1')
        z.writestr(NAME,'\n'.join(lines)+'\n')
        if withmeta:z.writestr(NAME[:-4]+'_meta.txt','lab: dummy\nserial: synthetic\n')
    f.seek(0)
    return f

class WindowGuards(unittest.TestCase):
    def test_equal_source_window_produces_exact_match(self):
        with ZipFile(source()) as z:a=read_matched_window(z,NAME)
        with ZipFile(source()) as z:b=read_matched_window(z,NAME)
        r=compare_windows(a,b)
        self.assertTrue(r['sampled_time_axis_exactly_equal'])
        self.assertEqual(r['exact_voltage_matches'],1100)
        self.assertTrue(r['exact_voltage_sequence_equal'])
    def test_equal_times_distinct_voltage_not_false_duplicate(self):
        with ZipFile(source(shift='0.0')) as z:a=read_matched_window(z,NAME)
        with ZipFile(source(shift='0.5')) as z:b=read_matched_window(z,NAME)
        r=compare_windows(a,b)
        self.assertFalse(r['exact_voltage_sequence_equal'])
        self.assertEqual(r['exact_voltage_matches'],0)
    def test_unmatched_time_axis_is_not_called_different_voltages(self):
        with ZipFile(source(rows=1100)) as z:a=read_matched_window(z,NAME)
        with ZipFile(source(rows=1101)) as z:b=read_matched_window(z,NAME)
        self.assertIsNone(compare_windows(a,b)['exact_voltage_matches'])
    def test_source_with_publisher_stage_folder_resolves_unique_basename(self):
        buf=io.BytesIO()
        with ZipFile(buf,'w') as z:
            lines=['run_time,c_vol,c_cur,step_type']
            lines.extend(f'{i},{4.2-i/100000},-0.1,1' for i in range(1100))
            z.writestr('Stage_1/TP_k01_05/'+NAME,'\n'.join(lines)+'\n')
            z.writestr('Stage_1/TP_k01_05/'+NAME[:-4]+'_meta.txt','lab: dummy\n')
        buf.seek(0)
        with ZipFile(buf) as z:
            result=read_matched_window(z,NAME)
        self.assertEqual(result['count'],1100)

    def test_missing_meta_fails_closed(self):
        with ZipFile(source(withmeta=False)) as z:
            with self.assertRaisesRegex(ValueError,'metadata'):read_matched_window(z,NAME)
    def test_short_source_fails_closed(self):
        with ZipFile(source(rows=999)) as z:
            with self.assertRaisesRegex(ValueError,'short'):read_matched_window(z,NAME)
    def test_decreasing_time_fails_closed(self):
        with ZipFile(source(reverse=True)) as z:
            with self.assertRaisesRegex(ValueError,'backwards'):read_matched_window(z,NAME)

if __name__=='__main__':unittest.main()