"""Source-format and scientific-claim guards; fixtures are explicitly synthetic."""
from __future__ import annotations
import io, unittest
from zipfile import ZipFile
from research.battery_curve_audit.figshare_k05_original_capacity import (
    analyze_new_cell, pinned_metadata, ORIGINALS
)

def make_csv(charge=4.0,discharge=4.0, malformed=False):
    s=['run_time,c_vol,c_cur,step_type']
    for i in range(80):
        t=i*60 if not (malformed and i==30) else -1
        s.append(f'{t},4.1,{charge},21')
    for i in range(80,160):
        s.append(f'{i*60},3.5,{-discharge},22')
    return '\n'.join(s)+'\n'

def fixture(*,missing=None,ambiguous=False,wrong_temp=None,wrong_point=None,
            wrong_serial=None,wrong_lab=None,reversed_dates=False,broken_time=False,
            charge_at=3.8, discharge_at=4.03):
    b=io.BytesIO()
    with ZipFile(b,'w') as z:
        for t in (10,23,45):
            for phase,idx in [('ET','01'),('AT','02')]:
                name=f'TP_k05_04_{idx}_{phase}_T{t}.csv'
                if name==missing:continue
                bad=broken_time and t==45 and phase=='AT'
                raw=make_csv(4,4) if phase=='ET' else make_csv(charge_at,discharge_at,malformed=bad)
                z.writestr(name,raw)
                lab='LAB_A' if not (wrong_lab==t and phase=='AT') else 'LAB_B'
                serial='CELL_A' if not (wrong_serial==t and phase=='AT') else 'CELL_B'
                temp=t if not (wrong_temp==t and phase=='AT') else 99
                point='k05' if not (wrong_point==t and phase=='AT') else 'k01noCU'
                date=('01.01.2025' if phase=='AT' else '01.01.2024')
                if reversed_dates:date='01.01.2024' if phase=='AT' else '01.01.2025'
                z.writestr(name[:-4]+'_meta.txt',
                           f'Laboratory identifier: {lab}\nInternal cell serial: {serial}\n'
                           f'Climate chamber temperature setpoint: {temp}°C\n'
                           f'Testpoint: {point}\nMeasurement start date: {date}\n')
        if ambiguous:
            name='TP_k05_04_03_AT_T10.csv';z.writestr(name,make_csv())
            z.writestr(name[:-4]+'_meta.txt','Laboratory identifier: LAB_A\nInternal cell serial: CELL_A\n')
    b.seek(0)
    return ZipFile(b)

class NewK05SourceTests(unittest.TestCase):
    def test_new_original_cell_has_three_explicit_temperature_pairs(self):
        with fixture() as z:
            r=analyze_new_cell(z,'TP_k05_04')
        self.assertEqual(len(r),3)
        self.assertEqual([x['temperature_C'] for x in r],[10,23,45])
        self.assertEqual(sum(x['original_csv_rows'] for x in r),960)
        self.assertTrue(all(x['source_date_chronology_checked'] for x in r))
        self.assertTrue(all(x['et_to_at_days']==366 for x in r))
        self.assertFalse(any(x['field_FPR_FNR_established'] for x in r))
    def test_mean_decrease_does_not_override_mixed_charge_discharge(self):
        with fixture(charge_at=3.8,discharge_at=4.03) as z:
            r=analyze_new_cell(z,'TP_k05_04')
        self.assertTrue(all(x['mean_change_percent']<0 for x in r))
        self.assertTrue(all(x['charge_change_percent']<0<x['discharge_change_percent'] for x in r))
        self.assertTrue(all(x['channel_direction']=='CHANNEL_DIRECTION_MISMATCH_REVIEW_REQUIRED' for x in r))
    def test_both_channels_declining_distinguished_from_mixed(self):
        with fixture(charge_at=3.8,discharge_at=3.9) as z:
            r=analyze_new_cell(z,'TP_k05_04')
        self.assertTrue(all(x['channel_direction']=='BOTH_CHANNELS_DECLINE_OBSERVED' for x in r))
    def test_missing_phase_never_extrapolated(self):
        with fixture(missing='TP_k05_04_02_AT_T23.csv') as z:
            with self.assertRaisesRegex(ValueError,'missing or ambiguous'):
                analyze_new_cell(z,'TP_k05_04')
    def test_duplicate_at_t10_never_chosen_arbitrarily(self):
        with fixture(ambiguous=True) as z:
            with self.assertRaisesRegex(ValueError,'missing or ambiguous'):
                analyze_new_cell(z,'TP_k05_04')
    def test_wrong_temperature_setpoint_rejected(self):
        with fixture(wrong_temp=45) as z:
            with self.assertRaisesRegex(ValueError,'temperature'):
                analyze_new_cell(z,'TP_k05_04')
    def test_wrong_calendar_nocu_label_rejected(self):
        with fixture(wrong_point=10) as z:
            with self.assertRaisesRegex(ValueError,'protocol label'):
                analyze_new_cell(z,'TP_k05_04')
    def test_wrong_serial_rejected(self):
        with fixture(wrong_serial=23) as z:
            with self.assertRaisesRegex(ValueError,'internal serial'):
                analyze_new_cell(z,'TP_k05_04')
    def test_wrong_lab_rejected(self):
        with fixture(wrong_lab=10) as z:
            with self.assertRaisesRegex(ValueError,'lab'):
                analyze_new_cell(z,'TP_k05_04')
    def test_reversed_true_dates_rejected(self):
        with fixture(reversed_dates=True) as z:
            with self.assertRaisesRegex(ValueError,'AT date not after ET'):
                analyze_new_cell(z,'TP_k05_04')
    def test_reversed_source_csv_time_rejected(self):
        with fixture(broken_time=True) as z:
            with self.assertRaisesRegex(ValueError,'clock not monotonic'):
                analyze_new_cell(z,'TP_k05_04')
    def test_other_cohort_not_accepted(self):
        with fixture() as z:
            with self.assertRaisesRegex(ValueError,'wrong new source cohort'):
                analyze_new_cell(z,'TP_k01_04')
    def test_offline_missing_complete_original_cohort_fails_without_network(self):
        import tempfile
        from pathlib import Path
        from research.battery_curve_audit.figshare_k05_original_capacity import run
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'unexpected/missing offline original archive'):
                run(offline_originals=Path(td))

    def test_offline_fake_original_byte_length_rejected(self):
        import tempfile
        from pathlib import Path
        from research.battery_curve_audit.figshare_k05_original_capacity import run, ORIGINALS
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            for _,name,_,_ in ORIGINALS:(p/name).write_bytes(b'not a licensed original ZIP')
            with self.assertRaisesRegex(ValueError,'offline original size/identity invalid'):
                run(offline_originals=p)

    def test_cannot_duplicate_offline_source_as_new_download(self):
        import tempfile
        from pathlib import Path
        from research.battery_curve_audit.figshare_k05_original_capacity import run
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'cannot save a second copy'):
                run(save_originals=Path(td),offline_originals=Path(td))

    def test_three_original_publisher_serials_are_distinct(self):
        from research.battery_curve_audit.figshare_k05_original_capacity import require_distinct_publisher_source_identities
        self.assertTrue(require_distinct_publisher_source_identities([('LAB_A','CELL_04'),('LAB_A','CELL_05'),('LAB_B','CELL_06')]))

    def test_cross_archive_duplicate_serial_rejected_case_and_whitespace_normalized(self):
        from research.battery_curve_audit.figshare_k05_original_capacity import require_distinct_publisher_source_identities
        with self.assertRaisesRegex(ValueError,'duplicate publisher lab/internal serial'):
            require_distinct_publisher_source_identities([('Lab_A','Serial_1'),(' Lab_A ',' serial_1 '),('Lab_A','Serial_3')])

    def test_incomplete_or_blank_cross_archive_identity_rejected(self):
        from research.battery_curve_audit.figshare_k05_original_capacity import require_distinct_publisher_source_identities
        with self.assertRaisesRegex(ValueError,'incomplete'):
            require_distinct_publisher_source_identities([('lab','one'),('lab','two')])
        with self.assertRaisesRegex(ValueError,'invalid'):
            require_distinct_publisher_source_identities([('lab','one'),('lab','two'),('','three')])

    def test_exact_publisher_pin_immutable_metadata_gate(self):
        f=[{'id':fid,'name':name,'size':size,'computed_md5':digest} for fid,name,size,digest in ORIGINALS]
        meta={'id':25975315,'doi':'10.6084/m9.figshare.25975315',
              'license':{'name':'CC BY 4.0','url':'https://creativecommons.org/licenses/by/4.0/'},
              'files':f}
        self.assertTrue(any(c['testpoint']=='TP_k05' for c in pinned_metadata(meta)['eligible_cohorts']))
        meta['files'][1]['computed_md5']='a'*32
        with self.assertRaisesRegex(ValueError,'pinned'):
            pinned_metadata(meta)
if __name__=='__main__':unittest.main()