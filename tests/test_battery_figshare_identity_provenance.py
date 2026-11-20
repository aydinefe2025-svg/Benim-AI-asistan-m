"""TDD: a publisher source-record join must never certify a physically verified cell."""
import io
import unittest
from zipfile import ZipFile
from research.battery_curve_audit.figshare_identity_provenance import (
    read_overview, verify_cell_directory, summarize_meta_sidecar, reconcile_records,
)

CSV_HEADER='serial_internal,serial,lab,tp,cell,stage\n'


def overview(rows):
    return (CSV_HEADER + '\n'.join(','.join(str(x) for x in row) for row in rows)+'\n').encode()


def sample_zip(serial='TP_k01_05', text='serial_internal: INT_123\nlab: LAB_A\ntp: k01\nstart: 2024-01-01\n'):
    f=io.BytesIO()
    with ZipFile(f,'w') as z:
        d=f'Stage_1/{serial}/'
        z.writestr(d+serial+'_01_ET_T23.csv','run_time,c_vol,c_cur,step_type\n')
        z.writestr(d+serial+'_01_ET_T23_meta.txt',text)
    f.seek(0)
    return f


class IdentityGuards(unittest.TestCase):
    def test_overview_uses_stage_and_serial_not_only_serial(self):
        rows=read_overview(overview([('INT_A','TP_k01_05','LAB_A','k01','05',1),('INT_B','TP_k01_05','LAB_B','k01','05',2)]))
        self.assertEqual(len(rows),2)
        self.assertIn(('1','TP_k01_05'),rows)
        self.assertIn(('2','TP_k01_05'),rows)
    def test_duplicate_composite_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            read_overview(overview([('INT_A','TP_k01_05','LAB_A','k01','05',1),('INT_B','TP_k01_05','LAB_B','k01','05',1)]))
    def test_no_missing_identity_accepted(self):
        with self.assertRaisesRegex(ValueError,'blank'):
            read_overview(overview([('INT_A','','LAB_A','k01','05',1)]))
    def test_archive_filename_has_exactly_one_paired_meta(self):
        with ZipFile(sample_zip()) as z:
            r=verify_cell_directory(z,'TP_k01_05')
        self.assertEqual(r['stage'],'1')
        self.assertEqual(r['serial'],'TP_k01_05')
    def test_stage_mismatch_not_silently_trusted(self):
        with ZipFile(sample_zip()) as z:
            r=verify_cell_directory(z,'TP_k01_05')
        rows=read_overview(overview([('INT_123','TP_k01_05','LAB_A','k01','05',2)]))
        out=reconcile_records(r,rows,summarize_meta_sidecar(b'serial_internal: INT_123\nlab: LAB_A\n'))
        self.assertEqual(out['decision'],'OVERVIEW_COMPOSITE_KEY_NOT_FOUND')
        self.assertFalse(out['physical_identity_authenticated'])
    def test_meta_labels_can_validate_two_separate_fields(self):
        with ZipFile(sample_zip()) as z:
            r=verify_cell_directory(z,'TP_k01_05')
        rows=read_overview(overview([('INT_123','TP_k01_05','LAB_A','k01','05',1)]))
        meta=summarize_meta_sidecar(b'serial_internal: INT_123\nlab: LAB_A\ntp: k01\n')
        out=reconcile_records(r,rows,meta)
        self.assertTrue(out['overview_composite_key_found'])
        self.assertTrue(out['sidecar_internal_id_matches_overview'])
        self.assertTrue(out['sidecar_lab_matches_overview'])
        self.assertFalse(out['physical_identity_authenticated'])
    def test_wrong_internal_cell_serial_not_accepted(self):
        with ZipFile(sample_zip()) as z:r=verify_cell_directory(z,'TP_k01_05')
        rows=read_overview(overview([('INT_123','TP_k01_05','LAB_A','k01','05',1)]))
        meta=summarize_meta_sidecar(b'serial_internal: INT_999\nlab: LAB_A\n')
        out=reconcile_records(r,rows,meta)
        self.assertFalse(out['sidecar_internal_id_matches_overview'])
        self.assertEqual(out['decision'],'SOURCE_METADATA_CONFLICT_REVIEW_REQUIRED')
    def test_no_paired_sidecar_fails_closed(self):
        f=io.BytesIO()
        with ZipFile(f,'w') as z:z.writestr('Stage_1/TP_k01_05/TP_k01_05_01_ET_T23.csv','head\n')
        f.seek(0)
        with ZipFile(f) as z:
            with self.assertRaisesRegex(ValueError,'paired'):
                verify_cell_directory(z,'TP_k01_05')
    def test_sidecar_unsafe_control_byte_not_accepted(self):
        with self.assertRaisesRegex(ValueError,'control'):
            summarize_meta_sidecar(b'lab: LAB_A\x00\n')
    def test_metadata_without_labels_does_not_invent_independence(self):
        meta=summarize_meta_sidecar(b'unknown freeform content without separators\n')
        with ZipFile(sample_zip()) as z:r=verify_cell_directory(z,'TP_k01_05')
        rows=read_overview(overview([('INT_123','TP_k01_05','LAB_A','k01','05',1)]))
        out=reconcile_records(r,rows,meta)
        self.assertFalse(out['sidecar_internal_id_matches_overview'])
        self.assertEqual(out['decision'],'SOURCE_METADATA_LINK_INCOMPLETE')
    def test_two_level_stage_folder_source_is_accepted_with_explicit_stage(self):
        f=io.BytesIO()
        with ZipFile(f,'w') as z:
            z.writestr('Stage_1/TP_k01_05_01_ET_T23.csv','run_time,c_vol\n')
            z.writestr('Stage_1/TP_k01_05_01_ET_T23_meta.txt','lab: LAB_A\n')
        f.seek(0)
        with ZipFile(f) as z:out=verify_cell_directory(z,'TP_k01_05')
        self.assertEqual(out['stage'],'1')
        self.assertEqual(out['stage_origin'],'source_path')

    def test_flat_source_with_no_stage_stays_unresolved(self):
        f=io.BytesIO()
        with ZipFile(f,'w') as z:
            z.writestr('TP_k01_05_01_ET_T23.csv','run_time,c_vol\n')
            z.writestr('TP_k01_05_01_ET_T23_meta.txt','lab: LAB_A\n')
        f.seek(0)
        with ZipFile(f) as z:location=verify_cell_directory(z,'TP_k01_05')
        self.assertIsNone(location['stage'])
        self.assertEqual(location['stage_origin'],'unavailable')
        rows=read_overview(overview([('INT_A','TP_k01_05','LAB_A','k01','05',1),('INT_B','TP_k01_05','LAB_B','k01','05',2)]))
        result=reconcile_records(location,rows,summarize_meta_sidecar(b'lab: LAB_A\n'))
        self.assertEqual(result['decision'],'STAGE_RECORD_PROVENANCE_INCOMPLETE')
        self.assertFalse(result['overview_composite_key_found'])

    def test_official_sidecar_field_names_join_unique_stage_without_zip_stage(self):
        f=io.BytesIO()
        with ZipFile(f,'w') as z:
            z.writestr('TP_k01_05_01_ET_T23.csv','run_time,c_vol\n')
            z.writestr('TP_k01_05_01_ET_T23_meta.txt','internal_cell_serial: INT_A\nlaboratory_identifier: LAB_A\ntestpoint: k01\n')
        f.seek(0)
        with ZipFile(f) as z:location=verify_cell_directory(z,'TP_k01_05')
        rows=read_overview(overview([('INT_A','TP_k01_05','LAB_A','k01','05',1),('INT_B','TP_k01_05','LAB_B','k01','05',2)]))
        result=reconcile_records(location,rows,summarize_meta_sidecar(b'internal_cell_serial: INT_A\nlaboratory_identifier: LAB_A\ntestpoint: k01\n'))
        self.assertTrue(result['overview_composite_key_found'])
        self.assertEqual(result['stage'],'1')
        self.assertEqual(result['stage_origin'],'sidecar_overview_unique_source_record')
        self.assertEqual(result['decision'],'SOURCE_RECORDS_CROSS_LINKED_NOT_PHYSICAL_AUTHENTICATION')
        self.assertFalse(result['physical_identity_authenticated'])

    def test_identical_sidecar_identifiers_across_stages_are_ambiguous(self):
        with ZipFile(sample_zip()) as z:location=verify_cell_directory(z,'TP_k01_05')
        location['stage']=None
        location['stage_origin']='unavailable'
        rows=read_overview(overview([('INT_A','TP_k01_05','LAB_A','k01','05',1),('INT_A','TP_k01_05','LAB_A','k01','05',2)]))
        meta=summarize_meta_sidecar(b'internal_cell_serial: INT_A\nlaboratory_identifier: LAB_A\n')
        result=reconcile_records(location,rows,meta)
        self.assertEqual(result['decision'],'SOURCE_METADATA_AMBIGUOUS_STAGE_REVIEW_REQUIRED')
        self.assertFalse(result['physical_identity_authenticated'])

    def test_sidecar_wrong_internal_fails_unique_stage_search(self):
        with ZipFile(sample_zip()) as z:location=verify_cell_directory(z,'TP_k01_05')
        location['stage']=None
        location['stage_origin']='unavailable'
        rows=read_overview(overview([('INT_A','TP_k01_05','LAB_A','k01','05',1),('INT_B','TP_k01_05','LAB_B','k01','05',2)]))
        result=reconcile_records(location,rows,summarize_meta_sidecar(b'internal_cell_serial: INT_WRONG\nlaboratory_identifier: LAB_A\n'))
        self.assertEqual(result['decision'],'SOURCE_METADATA_CONFLICT_REVIEW_REQUIRED')

    def test_crosswalk_diagnostic_counts_are_aggregate_only(self):
        with ZipFile(sample_zip()) as z:loc=verify_cell_directory(z,'TP_k01_05')
        loc['stage']=None
        loc['stage_origin']='unavailable'
        rows=read_overview(overview([('INT_A','TP_k01_05','LAB_A','k01','05',1),('INT_B','TP_k01_05','LAB_B','k01','05',2)]))
        meta=summarize_meta_sidecar(b'internal_cell_serial: INT_A\nlaboratory_identifier: LAB_A\ntestpoint: k01\n')
        out=reconcile_records(loc,rows,meta)
        diag=out['diagnostic_matching_row_counts']
        self.assertEqual(diag['overview_same_archive_serial'],2)
        self.assertEqual(diag['overview_matching_internal_serial'],1)
        self.assertEqual(diag['overview_matching_lab'],1)
        self.assertEqual(diag['overview_matching_testpoint'],2)
        self.assertEqual(diag['overview_same_archive_serial_internal_and_lab'],1)
        self.assertTrue(all(isinstance(x,int) for x in diag.values()))

    def test_filename_ambiguous_across_zip_fails_closed(self):
        f=io.BytesIO()
        with ZipFile(f,'w') as z:
            for folder in ('Stage_1/TP_k01_05/','Stage_2/TP_k01_05/'):
                z.writestr(folder+'TP_k01_05_01_ET_T23.csv','h\n')
                z.writestr(folder+'TP_k01_05_01_ET_T23_meta.txt','lab: LAB_A')
        f.seek(0)
        with ZipFile(f) as z:
            with self.assertRaisesRegex(ValueError,'ambiguous'):
                verify_cell_directory(z,'TP_k01_05')

if __name__=='__main__':unittest.main()