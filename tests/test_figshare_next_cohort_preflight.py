import unittest
from research.battery_curve_audit.figshare_next_cohort_preflight import inspect_metadata


def source(c=3):
    files=[]
    fid=47639005
    for test in (1,2,3):
        for i in range(4,4+c):
            files.append({'id':fid,'name':f'TP_k{test:02d}_{i:02d}.zip','size':7100000,
                          'computed_md5':f'{fid:032x}'})
            fid+=1
    return {'id':25975315,'doi':'10.6084/m9.figshare.25975315',
            'license':{'name':'CC BY 4.0','url':'https://creativecommons.org/licenses/by/4.0/'},'files':files}

class PreflightTests(unittest.TestCase):
    def test_new_publisher_full_triplet_but_never_repeat_k01(self):
        d=inspect_metadata(source())
        self.assertEqual(d['eligible_full_three_cell_cohorts'],2)
        self.assertEqual(d['chosen_cohort']['testpoint'],'TP_k02')
        self.assertFalse(d['next_source_zip_downloaded'])
        self.assertEqual(d['real_measurements_examined'],0)
    def test_incomplete_triplet_rejected(self):
        a=source();a['files']=[x for x in a['files'] if x['name']!='TP_k02_06.zip']
        self.assertEqual(inspect_metadata(a)['eligible_full_three_cell_cohorts'],1)
    def test_large_input_triplet_skipped(self):
        a=source();a['files'][4]['size']=16_000_000
        self.assertEqual(inspect_metadata(a)['chosen_cohort']['testpoint'],'TP_k03')
    def test_source_name_collision_detected_not_silently_overwritten(self):
        a=source();a['files'][4]['name']=a['files'][3]['name']
        r=inspect_metadata(a)
        self.assertEqual(r['publisher_duplicate_filename_count'],1)
        self.assertEqual(r['eligible_full_three_cell_cohorts'],1)
        self.assertEqual(r['chosen_cohort']['testpoint'],'TP_k03')
    def test_source_id_duplication_rejected(self):
        a=source();a['files'][1]['id']=a['files'][0]['id']
        with self.assertRaisesRegex(ValueError,'duplicate'):inspect_metadata(a)
    def test_forged_publisher_rejected(self):
        a=source();a['id']=1
        with self.assertRaisesRegex(ValueError,'article'):inspect_metadata(a)
    def test_forged_license_rejected(self):
        a=source();a['license']['name']='proprietary'
        with self.assertRaisesRegex(ValueError,'licence'):inspect_metadata(a)
    def test_unsafe_path_rejected(self):
        a=source();a['files'][0]['name']='../TP_k01_04.zip'
        with self.assertRaisesRegex(ValueError,'unsafe'):inspect_metadata(a)
if __name__=='__main__': unittest.main()