"""New independent Bayreuth specimens: file provenance + genuine I*dt controls."""
import hashlib
import io
import json
import unittest
import zipfile
from unittest.mock import patch
from research.battery_curve_audit import bayreuth_additional_three_originals as m

HEADER = '~Time[h],DataSet,t-Step[h],t-Set[h],Line,Command,U[V],I[A],Ah[Ah],Ah-Step,Wh[Wh],Cyc-Count,State\n'

def synthetic_zip(cell='F0007', offset=0, malformed=False):
    def checkup(stage):
        lines=[];t=0;index=1
        definitions=[('Discharge',17,-.12,.12,4.18,3.0,1),('Charge',15,.121,.121,3.03,4.2,1),
                     ('Discharge',29,-.06,.12,4.18,3.0,2),('Charge',27,.0605,.121,3.04,4.2,2)]
        for name,plan,cur,ah,start,end,dur in definitions:
            line=plan+(offset if stage=='m0001' else 0)
            sign=-1 if cur<0 else 1
            for k in range(4):
                th=dur*k/3
                voltage=start+(end-start)*k/3
                throughput=sign*ah*k/3
                lines.append(f'{t+th:.8f},{index},{th:.8f},{th:.8f},{line},{name},{voltage:.5f},{cur:.6f},0,{throughput:.7f},0,1,1')
                index+=1
            t+=dur+.04
        return HEADER+'\n'.join(lines)+'\n'
    buff=io.BytesIO()
    with zipfile.ZipFile(buff,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr(f'{cell}/M0001_checkup.txt',checkup('m0001'))
        z.writestr(f'{cell}/M0003_checkup.txt',checkup('m0003'))
        if malformed:
            z.writestr('../escape.txt','abc')
    return buff.getvalue()

class TestAdditionalSpecimens(unittest.TestCase):
    def test_official_publisher_pin_unique_and_separate(self):
        self.assertEqual(set(m.ADDITIONAL_SOURCE_FILES), {'F0007','F0022','F0138'})
        self.assertFalse(set(m.ADDITIONAL_SOURCE_FILES)&{'F0001','F0002'})
        for s in m.ADDITIONAL_SOURCE_FILES.values():
            self.assertEqual(len(s['md5']),32)
            self.assertGreater(s['size'],15_000_000)

    def test_bol_eol_genuine_native_independent_current_integral(self):
        b=synthetic_zip(offset=6)
        spec={'size':len(b),'md5':hashlib.md5(b).hexdigest()}
        x=m.analyze_original_blob('F0007', b, spec)
        self.assertTrue(x['zip_crc_pass'])
        self.assertEqual(x['stage_line_offset_alignment']['beginning_minus_ending_plan_line_offset'],6)
        self.assertEqual(x['stage_line_offset_alignment']['matched_discharge_line_pairs'],2)
        self.assertEqual(x['stage_line_offset_alignment']['matched_charge_line_pairs'],2)
        for phase in ('charge','discharge'):
            q=x['paired_measurement'][phase]
            self.assertTrue(q['comparable_homologous_source_step'])
            self.assertAlmostEqual(q['independently_integrated_trapezoid_delta_mAh'],0.,places=4)
            self.assertAlmostEqual(q['source_step_delta_mAh'],0.,places=4)
            self.assertTrue(q['not_a_certified_capacity_loss'])

    def test_mismatched_publisher_md5_rejected(self):
        b=synthetic_zip()
        with self.assertRaisesRegex(ValueError, 'MD5'):
            m.analyze_original_blob('F0007',b,{'size':len(b),'md5':'0'*32})

    def test_zip_path_traversal_rejected(self):
        b=synthetic_zip(malformed=True)
        with self.assertRaisesRegex(ValueError, 'traversal'):
            m.analyze_original_blob('F0007',b,{'size':len(b),'md5':hashlib.md5(b).hexdigest()})

    def test_byte_size_rejected(self):
        b=synthetic_zip()
        with self.assertRaisesRegex(ValueError, 'byte-count'):
            m.analyze_original_blob('F0007',b,{'size':len(b)+2,'md5':hashlib.md5(b).hexdigest()})

    def test_different_source_without_homologous_steps_is_not_forced(self):
        b=synthetic_zip()
        spec={'size':len(b),'md5':hashlib.md5(b).hexdigest()}
        with patch.object(m.core,'infer_stage_line_offset',return_value={'offset_inferred':False,'reason':'no matching physiology'}):
            x=m.analyze_original_blob('F0007',b,spec)
        self.assertFalse(x['paired_measurement']['discharge']['comparable'])
        self.assertNotIn('source_step_delta_mAh',x['paired_measurement']['discharge'])

    def test_summary_preserves_source_grain_and_no_calibration_claim(self):
        blobs={}
        for cell in m.ADDITIONAL_SOURCE_FILES:
            b=synthetic_zip(cell)
            blobs[cell]=(b,{'size':len(b),'md5':hashlib.md5(b).hexdigest()})
        with patch.dict(m.ADDITIONAL_SOURCE_FILES,{cell:spec for cell,(b,spec) in blobs.items()},clear=True):
            d=m.analyze_additions({cell:b for cell,(b,spec) in blobs.items()})
        self.assertEqual(d['new_independent_source_cell_count'],3)
        self.assertTrue(d['instrument_calibration_not_verified'])
        self.assertTrue(d['not_full_48_cell_population'])
        self.assertFalse(d['same_cells_as_Stroebl'])
        self.assertEqual(sum(bool(q['paired_measurement']['discharge']['comparable_homologous_source_step']) for q in d['cells'].values()),3)
        self.assertFalse(d['quantifies_aging_causality'])

if __name__=='__main__':
    unittest.main()