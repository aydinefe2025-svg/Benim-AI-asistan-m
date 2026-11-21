"""Synthetic-only regression cases; real-source values evaluated by CI separately."""
from __future__ import annotations
import io
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from research.battery_curve_audit.figshare_six_source_curve_screen import (
    PINS, PHASES, TOLERANCE_MV, DURATION_FRACTION,
    phase_pair_max_mV, compare_source_pair, read_phases, benchmark,
    load_archive_directory,
)


def profile(*,duration=1000.0,offset=0.0):
    return tuple((i*duration/100, 3.0+i*.01+offset) for i in range(101))

def view(cell='a',stage='ET',temp=23,phase=21,p=None):
    return {'cell':cell,'stage':stage,'temperature_C':temp,'phase':phase,'points':p or profile()}


def fake_source(*,bad_time=False,wrong_temp=False,missing_phase=False,conflict=False):
    def line(t,vol,cur,step):return f'{t//3600}:{t%3600//60:02d}:{t%60:02d}.0000,{vol},{cur},{step}'
    rows=['run_time,c_vol,c_cur,step_type']
    for i in range(400):rows.append(line(i*10,3.5,0,0))
    for i in range(60):
        t=(399+i)*10 if not bad_time or i!=40 else (399+20)*10
        rows.append(line(t,3.3+i*.01,1,21))
    if not missing_phase:
        for i in range(60):
            rows.append(line((459+i)*10,4-i*.01,-1,22))
    else:
        for i in range(60):
            rows.append(line((459+i)*10,3.5,0,0))
    if conflict:
        rows.append(line(5180,3.4,-1,22))
    b=io.BytesIO()
    with ZipFile(b,'w') as z:
        csvname='TP_k04_04_01_ET_T23.csv'
        z.writestr(csvname,'\n'.join(rows)+'\n')
        z.writestr(csvname[:-4]+'_meta.txt',
            'Laboratory identifier: LAB1\nInternal cell serial: A\nClimate chamber temperature setpoint: '+('45°C' if wrong_temp else '23°C')+'\n')
    return ZipFile(io.BytesIO(b.getvalue()))

class RealSourceSixRecordAuditTests(unittest.TestCase):
    def test_threshold_is_fixed_before_source_review(self):
        self.assertEqual(TOLERANCE_MV,2.0)
        self.assertEqual(DURATION_FRACTION,.005)
    def test_exact_copy_of_real_shape_is_replay_positive(self):
        x=view('a');y=view('replay')
        self.assertTrue(compare_source_pair(x,y)['near_match'])
        self.assertEqual(compare_source_pair(x,y)['max_absolute_voltage_difference_mV'],0)
    def test_slight_voltage_shift_passes_predeclared_near_rule(self):
        a=view('a');b=view('b',p=profile(offset=.0012))
        self.assertTrue(compare_source_pair(a,b)['near_match'])
    def test_over_two_millivolts_is_not_near(self):
        a=view('a');b=view('b',p=profile(offset=.0021))
        self.assertFalse(compare_source_pair(a,b)['near_match'])
    def test_duration_mismatch_rejects_even_identical_progress_shape(self):
        a=view('a');b=view('b',p=profile(duration=1100.))
        self.assertFalse(compare_source_pair(a,b)['near_match'])
    def test_same_cell_does_not_count_as_negative(self):
        with self.assertRaisesRegex(ValueError,'same source ID'):
            compare_source_pair(view('a'),view('a'))
    def test_incompatible_temperature_or_mode_rejected(self):
        with self.assertRaisesRegex(ValueError,'noncomparable'):
            compare_source_pair(view('a'),view('b',temp=45))
        with self.assertRaisesRegex(ValueError,'noncomparable'):
            compare_source_pair(view('a'),view('b',phase=22))
    def test_short_curve_rejected(self):
        with self.assertRaisesRegex(ValueError,'incomplete source phase'):
            phase_pair_max_mV(tuple((i,float(i)) for i in range(10)),profile())
    def test_duplicate_phase_time_rejected(self):
        bad=list(profile());bad[30]=(bad[29][0],bad[30][1])
        with self.assertRaisesRegex(ValueError,'nonmonotone'):
            phase_pair_max_mV(tuple(bad),profile())
    def test_source_parser_accepts_two_realistic_synthetic_phases(self):
        with fake_source() as z:
            s=read_phases(z,'TP_k04_04_01_ET_T23.csv',cell='TP_k04_04',stage='ET',temp=23)
        self.assertEqual(s['raw_csv_rows'],520)
        self.assertEqual({p:len(s['phases'][p]) for p in PHASES},{21:60,22:60})
    def test_wrong_source_temperature_rejected(self):
        with fake_source(wrong_temp=True) as z:
            with self.assertRaisesRegex(ValueError,'climate chamber temperature'):
                read_phases(z,'TP_k04_04_01_ET_T23.csv',cell='TP_k04_04',stage='ET',temp=23)
    def test_reversed_original_phase_time_rejected(self):
        with fake_source(bad_time=True) as z:
            with self.assertRaisesRegex(ValueError,'phase clock'):
                read_phases(z,'TP_k04_04_01_ET_T23.csv',cell='TP_k04_04',stage='ET',temp=23)
    def test_missing_discharge_phase_rejected(self):
        with fake_source(missing_phase=True) as z:
            with self.assertRaisesRegex(ValueError,'incomplete/multiple'):
                read_phases(z,'TP_k04_04_01_ET_T23.csv',cell='TP_k04_04',stage='ET',temp=23)
    def test_real_originals_required_not_synthetic_pretending_to_be_field(self):
        with self.assertRaisesRegex(ValueError,'six publisher archive cohort'):
            benchmark({})
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'exactly six original files'):
                load_archive_directory(Path(td))
    def test_wrong_digest_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            for _,name,_,_ in PINS:(p/name).write_bytes(b'fake')
            with self.assertRaisesRegex(ValueError,'wrong original source'):
                load_archive_directory(p)

if __name__=='__main__':unittest.main()