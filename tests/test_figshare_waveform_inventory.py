"""Synthetic guard tests for original Figshare waveform candidate inventory."""
import copy
import unittest
from research.battery_curve_audit.figshare_waveform_inventory import analyze_inventory


def article():
    return {'id':25975315,'doi':'10.6084/m9.figshare.25975315.v1',
            'license':{'name':'CC BY 4.0','url':'https://creativecommons.org/licenses/by/4.0/'},
            'files':[{'id':10,'name':'a.zip','size':8_000,'computed_md5':'a'*32},
                     {'id':11,'name':'a.zip','size':4_000,'computed_md5':'b'*32},
                     {'id':12,'name':'b.zip','size':200_000_000,'computed_md5':'c'*32},
                     {'id':13,'name':'experiments_meta.csv','size':350,'computed_md5':'d'*32}]}


class InventoryGuards(unittest.TestCase):
    def test_sorted_id_based_candidates_even_with_duplicate_names(self):
        out=analyze_inventory(article())
        self.assertEqual([x['file_id'] for x in out['bounded_candidates_first_20']],[13,11,10])
        self.assertEqual(out['bounded_archive_candidates_count'],3)
        self.assertEqual(out['publisher_listed_total_bytes'],200_012_350)
        self.assertFalse(out['production_release_allowed'])
        self.assertEqual(out['independent_physical_cells_verified'],0)
        self.assertEqual(out['original_waveform_files_downloaded'],0)
    def test_no_raw_files_in_budget_is_reported_not_accepted(self):
        m=article()
        m['files']=[{'id':8,'name':'one.zip','size':120_000_000,'computed_md5':'a'*32}]
        out=analyze_inventory(m)
        self.assertEqual(out['decision'],'NO_CANDIDATE_WITHIN_BUDGET_METADATA_ONLY')
        self.assertEqual(out['smallest_potential_signal_file_bytes'],120_000_000)
    def test_wrong_doi_refused(self):
        m=article();m['doi']='10.6084/m9.figshare.123456'
        with self.assertRaisesRegex(ValueError,'DOI'): analyze_inventory(m)
    def test_wrong_license_refused(self):
        m=article();m['license']['name']='CC BY NC 4.0'
        with self.assertRaisesRegex(ValueError,'license'): analyze_inventory(m)
    def test_license_hostname_spoofing_refused(self):
        m=article();m['license']['url']='https://creativecommons.org.attacker.invalid/licenses/by/4.0'
        with self.assertRaisesRegex(ValueError,'license'): analyze_inventory(m)
    def test_bad_filename_refused(self):
        m=article();m['files'][0]['name']='../../unsafe.zip'
        with self.assertRaisesRegex(ValueError,'filename'): analyze_inventory(m)
    def test_duplicate_file_id_refused(self):
        m=article();m['files'][1]['id']=10
        with self.assertRaisesRegex(ValueError,'file id'): analyze_inventory(m)
    def test_missing_md5_excluded_not_trusted(self):
        m=article();m['files'][0]['computed_md5']='not_md5'
        out=analyze_inventory(m)
        self.assertNotIn(10,[x['file_id'] for x in out['bounded_candidates_first_20']])
    def test_oversize_budget_rejected(self):
        with self.assertRaisesRegex(ValueError,'trial budget'): analyze_inventory(article(),trial_cap=999_999_999)
    def test_bad_size_rejected(self):
        m=article();m['files'][0]['size']=True
        with self.assertRaisesRegex(ValueError,'size'): analyze_inventory(m)
    def test_names_are_public_metadata_not_verified_cells(self):
        o=analyze_inventory(article())
        self.assertFalse(o['waveform_cell_id_link_verified'])
        self.assertFalse(o['field_false_match_rate_established'])
        self.assertIsNone(o.get('real_fpr'))

if __name__=='__main__': unittest.main()