import hashlib
import itertools
import json
import pathlib
import unittest
from unittest.mock import patch
from research.battery_curve_audit import graz_eis_group_geometry_audit as mod

FIXTURE=pathlib.Path(__file__).resolve().parents[1]/'research/battery_curve_audit/verified_eis_10_cells_829_derived_ledger.json'
class GrazGeometryTests(unittest.TestCase):
    def setUp(self):
        self.doc=mod.read_ledger(FIXTURE.read_bytes())
    def test_ten_real_original_cells_and_five_stages(self):
        self.assertEqual(len(self.doc['cells']),10)
        self.assertEqual(mod.analyse_ledger(self.doc)['source_cells_analysed'],10)
        self.assertEqual(len(mod.analyse_ledger(self.doc)['results']),12)
    def test_pin_rejects_changed_value(self):
        s=FIXTURE.read_bytes().replace(b'EIS_C02.xlsx',b'EIS_C00.xlsx')
        self.assertNotEqual(s,FIXTURE.read_bytes())
        with self.assertRaises(ValueError):mod.read_ledger(s)
    def test_pin_rejects_truncation(self):
        with self.assertRaises(ValueError):mod.read_ledger(FIXTURE.read_bytes()[:-1])
    def test_source_cell_names_reject_duplicate(self):
        doc=json.loads(FIXTURE.read_text());doc['cells'][0]['filename']=doc['cells'][1]['filename']
        with self.assertRaises(ValueError):mod.read_ledger(json.dumps(doc).encode())
    def test_permutation_exact_total_and_bounded(self):
        d={k:float(i) for i,k in enumerate(mod.IDS_A+mod.IDS_B)}
        r=mod.exact_partition_sensitivity(d)
        self.assertEqual(r['possible_label_partitions'],252)
        self.assertGreater(r['two_sided_complete_label_permutation_sensitivity'],0)
        self.assertLessEqual(r['two_sided_complete_label_permutation_sensitivity'],1)
    def test_wrong_group_missing_cell(self):
        with self.assertRaises(ValueError):mod.exact_partition_sensitivity({mod.IDS_A[0]:1.})
    def test_uncalibrated_and_capacities_not_claimed(self):
        x=mod.analyse_ledger(self.doc)
        for k in ('physical_diameter_assignment_verified','physical_causation_established','capacity_change_measured','real_instrument_calibration_verified','production_release_allowed'):
            self.assertIs(x[k],False)
    def test_original_readme_bad_md5(self):
        md={'id':mod.RECORD,'files':[{'key':'ReadME.txt','checksum':'md5:'+mod.README_MD5}]+[{'key':str(i)} for i in range(10)]}
        with self.assertRaises(ValueError):mod.verify_original_readme(md,b'falsified readme')
    def test_original_readme_wrong_record(self):
        md={'id':mod.RECORD+1,'files':[{'key':'ReadME.txt','checksum':'md5:'+mod.README_MD5}]+[{'key':str(i)} for i in range(10)]}
        with self.assertRaises(ValueError):mod.verify_original_readme(md,b'falsified readme')
    def test_nonfinite_permutation_rejected(self):
        d={k:0.1 for k in mod.IDS_A+mod.IDS_B};d[mod.IDS_A[0]]=float('nan')
        with self.assertRaises(ValueError):mod.exact_partition_sensitivity(d)
    def test_readme_url_nonzenodo_rejected(self):
        with self.assertRaises(ValueError):mod.get_bytes('https://example.com/bad',3000)
    def test_stage_output_not_geometry_inference(self):
        report=mod.analyse_ledger(self.doc)
        self.assertTrue(all(x['permutation_exchangeability_not_verified'] for x in report['results']))
        self.assertFalse(report['physical_diameter_assignment_verified'])

    def test_verified_original_readme_hard_pinned_mapping(self):
        p=pathlib.Path(__file__).resolve().parents[1]/'research/battery_curve_audit/publisher_verified_zenodo_original_ReadME.txt'
        raw=p.read_bytes()
        self.assertEqual(hashlib.md5(raw).hexdigest(),mod.README_MD5)
        md={'id':mod.RECORD,'files':[{'key':'ReadME.txt','checksum':'md5:'+mod.README_MD5}]+[{'key':str(i)} for i in range(10)]}
        v=mod.verify_original_readme(md,raw)
        self.assertTrue(v['original_publisher_readme_mapping_verified'])
        self.assertEqual(v['publisher_documented_groups'][0]['original_specimen_ids'],['C02','C03','C04','C05','C06'])
        self.assertEqual(v['publisher_documented_groups'][0]['indenter_diameter_mm'],30)
        self.assertEqual(v['publisher_documented_groups'][1]['indenter_diameter_mm'],180)
        self.assertIs(v['independent_physical_custody_witness_verified'],False)
    def test_false_180_on_02_mapping_rejected_even_if_text_looks_near(self):
        p=pathlib.Path(__file__).resolve().parents[1]/'research/battery_curve_audit/publisher_verified_zenodo_original_ReadME.txt'
        source=p.read_text()
        with self.assertRaises(ValueError):mod.parse_readme_published_impactor_mapping(source.replace('30 mm','180 mm'))
    def test_duplicate_geometry_lines_rejected(self):
        p=pathlib.Path(__file__).resolve().parents[1]/'research/battery_curve_audit/publisher_verified_zenodo_original_ReadME.txt'
        with self.assertRaises(ValueError):mod.parse_readme_published_impactor_mapping(p.read_text()+'\nCell 09-13: hemispherical impactor d= 180 mm')
    def test_geometry_assignment_requires_actual_source_text(self):
        with self.assertRaises(ValueError):mod.parse_readme_published_impactor_mapping('C02-C06 look negative at 10Hz therefore 30mm')
if __name__=='__main__':unittest.main()
