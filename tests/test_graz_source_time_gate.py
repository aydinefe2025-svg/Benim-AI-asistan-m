import unittest, datetime as dt
from research.battery_curve_audit import graz_source_time_gate as m

def timetok(yyyy,mo,da,hh,mi,ss):return f'{yyyy:04d}-{mo:02d}-{da:02d}_{hh:02d}-{mi:02d}-{ss:02d}-000000'
def sample():
    rows=[]
    for cell,(yyyy,mm,dd) in [('02',(2024,10,28)),('03',(2025,9,4))]:
        start=dt.datetime(yyyy,mm,dd,10,0,0)
        end=start+dt.timedelta(days=2)
        rows.append({'path':f'Fresh cell {cell}/data.log','cell_id_from_name_only':cell,
                     'candidate_role_from_name_only':'charge_discharge_log_candidate',
                     'first_electrical_time_token':timetok(start.year,start.month,start.day,10,0,0),
                     'last_electrical_time_token':timetok(end.year,end.month,end.day,10,0,0)})
        for delay in (0,1,3):
            d=start+dt.timedelta(days=delay,minutes=10)
            path=f'Fresh cell {cell}/SP_NEMO_{d.day:02d}_{d.month:02d}_{d.year:04d}_{d.hour:02d}_{d.minute:02d}_{d.second:02d}_logfile.txt'
            rows.append({'path':path,'cell_id_from_name_only':cell,'candidate_role_from_name_only':'thickness_sp_candidate',
                         'metadata_line_clues':[{'text':f'Start time : {m.vienna_epoch(d)}'}]})
    return {'source_doi':'10.5281/zenodo.22079387','publisher_zip_md5_verified':True,'zip_crc_verified':True,
            'original_zip_sha256':'sha256placeholder','members':rows}

class TestGate(unittest.TestCase):
    def test_phases_are_start_candidates_not_certification(self):
        d=m.verify_starts(sample())
        self.assertEqual((d['all_cartesian_log_sp_pairs'],d['source_label_wrong_cell_pairs'],
                          d['same_cell_sp_starts_outside_log'],d['same_cell_sp_starts_inside_log_candidates']), (12,6,2,4))
        self.assertFalse(d['experiment_phase_alignment_certified'])
    def test_windows_without_tzdb_and_vienna_dst_boundaries(self):
        self.assertEqual(m.vienna_epoch(dt.datetime(2024, 10, 28, 10)),
                         dt.datetime(2024, 10, 28, 9, tzinfo=dt.timezone.utc).timestamp())
        self.assertEqual(m.vienna_epoch(dt.datetime(2025, 9, 4, 10)),
                         dt.datetime(2025, 9, 4, 8, tzinfo=dt.timezone.utc).timestamp())
        with self.assertRaisesRegex(ValueError, 'DST'):
            m.vienna_epoch(dt.datetime(2024, 10, 27, 2, 30))
        with self.assertRaisesRegex(ValueError, 'DST'):
            m.vienna_epoch(dt.datetime(2025, 3, 30, 2, 30))
    def test_no_source_hash_proof_reject(self):
        s=sample();s['publisher_zip_md5_verified']=False
        with self.assertRaisesRegex(ValueError,'checksum'):m.verify_starts(s)
    def test_missing_stage_file_reject(self):
        s=sample();s['members'].pop()
        with self.assertRaisesRegex(ValueError,'file set'):m.verify_starts(s)
    def test_conflicting_SP_filename_epoch_reject(self):
        s=sample()
        s['members'][1]['metadata_line_clues'][0]['text']='Start time : 1'
        with self.assertRaisesRegex(ValueError,'not consistent'):m.verify_starts(s)

if __name__=='__main__':unittest.main()