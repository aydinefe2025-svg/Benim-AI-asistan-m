"""Scientific source integrity, independent specimen LOO, and physical safety boundaries."""
import math,unittest
from research.battery_curve_audit import graz_eis_physical_stage_transfer as m
try:import numpy as np
except ImportError:np=None


def synthetic_cells():
    f=[10**(5-i*.07) for i in range(101)]
    out=[]
    for j in range(10):
        z0=[0.005+0.01/(1+1j*2*math.pi*hz*.01)+1j*2*math.pi*hz*.0000001 for hz in f]
        tabs={}
        for k,stage in enumerate(m.LEVELS):
            z=[v+0.0005*k*(1+0.1*math.sin(j))*(1/(1+1j*2*math.pi*hz*.02)) for hz,v in zip(f,z0)]
            tabs[stage]=[(hz,abs(v),math.degrees(math.atan2(v.imag,v.real))) for hz,v in zip(f,z)]
        out.append({'name':f'EIS_C{(j+2 if j<5 else j+4):02}.xlsx',
                    'original_sha256':f'{j+1:064x}',
                    'publisher_md5_crc_verified':True,'diameter_mm':30 if j<5 else 180,
                    'tables':tabs})
    return out

class PhysicalSource(unittest.TestCase):
    def test_original_source_contract(self):self.assertTrue(m.validate_original_cells(synthetic_cells()))
    def test_duplicate_source_specimen_rejected(self):
        x=synthetic_cells();x[1]['name']=x[0]['name']
        with self.assertRaises(ValueError):m.validate_original_cells(x)
    def test_unmatched_original_frequency_rejected(self):
        x=synthetic_cells();r=x[0]['tables'][m.STAGES[0]][7];x[0]['tables'][m.STAGES[0]][7]=(r[0]*1.001,r[1],r[2])
        with self.assertRaises(ValueError):m.validate_original_cells(x)
    def test_wrong_geometry_group_rejected(self):
        x=synthetic_cells();x[0]['diameter_mm']=180
        with self.assertRaises(ValueError):m.validate_original_cells(x)
    def test_exact_sign_tail(self):
        self.assertEqual(m.exact_two_sided_sign_p(10,10),2/1024)
        self.assertEqual(m.exact_two_sided_sign_p(5,10),1)
    @unittest.skipUnless(np is not None,'numpy available in dedicated source CI')
    def test_loo_excludes_entire_specimen(self):
        f=np.zeros((10,4,101),complex)
        for j in range(10):
            for k in range(4):f[j,k,:]=(k+1)*(.1+1j*.02)*(1+.01*j)
        p=m.leave_one_specimen_out(f)
        self.assertEqual(len(p),40)
        self.assertTrue(all(x['heldout_specimen_index'] not in x['training_specimen_indices'] for x in p))
        self.assertEqual(sum(x['predicted_stage_index']==x['true_stage_index'] for x in p),40)
    @unittest.skipUnless(np is not None,'numpy available in dedicated source CI')
    def test_geometry_specific_has_only_four_training_specimens(self):
        f=np.zeros((10,4,101),complex)
        p=m.leave_one_specimen_out(f,[30]*5+[180]*5)
        self.assertTrue(all(len(x['training_specimen_indices'])==4 for x in p))
        self.assertTrue(all(x['heldout_specimen_index'] not in x['training_specimen_indices'] for x in p))
    @unittest.skipUnless(np is not None,'numpy available in dedicated source CI')
    def test_full_synthetic_source_40_predictions_and_safety_flags(self):
        out,raw=m.compute(synthetic_cells(),permutations=100)
        self.assertEqual(out['original_source_eis_triplets'],5050)
        self.assertEqual(len(raw),5050)
        self.assertEqual(len(out['heldout_specimen_predictions']),80)
        self.assertTrue(all(x['no_test_specimen_training'] for x in out['heldout_specimen_predictions']))
        self.assertEqual(out['stage95_shift_greater_than_stage25_cell_count'],10)
        self.assertEqual(out['stage95_vs_stage25_exact_two_sided_sign_p'],.00195312)
        self.assertFalse(out['production_release_allowed'])
        self.assertFalse(out['independent_instrument_calibration_verified'])
        self.assertFalse(out['actual_capacity_Ah_measured'])
    @unittest.skipUnless(np is not None,'numpy available in dedicated source CI')
    def test_no_bad_shape_or_unbounded_model(self):
        with self.assertRaises(ValueError):m.leave_one_specimen_out(np.zeros((10,5,101),complex))
    def test_null_p_not_implicitly_significant(self):self.assertEqual(m.exact_two_sided_sign_p(0,10),.001953125)

if __name__=='__main__':unittest.main()