import copy
import unittest
from pathlib import Path
import f80_rotation_acceptance as f

class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tov={'model':f.MODEL,'status':'PASS_NUMERICAL_HYBRID_EOS_CANDIDATE_PHYSICAL_ACCEPTANCE_NOT_ESTABLISHED',
                  'source':{'original_sources_modified':False},
                  'TOV':{'M2p073':{'M_msun':2.07300001,'R_km':12.39978913}}}
        self.raw={'model':f.MODEL,'schema':'J0740_BPS_MPA1_RNS_V1','rns_source':{'commit':f.RNS_COMMIT},
                  'status':'PASS_RNS_TWO_GRID_CONVERGENCE',
                  'rns_eos_export':{'sha256':f.EXPECTED_EOS_SHA},'RNS_runs':[]}
        for grid, radius, binary in [('151x301',12.50,'a'*64),('201x401',12.502,'b'*64)]:
            self.raw['RNS_runs'].append({'rns_binary_sha256':binary,'result':{
                'grid':grid,'status':'PASS','M_msun':2.073,'R_equatorial_km':radius,
                'spin_hz':346.55,'rho_c_g_cm3':1.10e15}})
    def check(self):return f.validate(self.raw,self.tov,rns_table_path=Path('unused'),enforce_sha=False)
    def test_synthetic_two_distinct_grids_math_acceptance_only(self):
        x=self.check();self.assertEqual(x['result'],'REAL_C_ROTATING_GR_TWO_GRID_PASS_NUMERICAL_ONLY')
        self.assertEqual(x['source_native_XPSI_photon_likelihood'],'NOT_RUN')
        self.assertEqual(x['global_rotation_stability'],'NOT_ESTABLISHED')
        self.assertEqual(x['grid_delta_R_m'],2.000000000000668)
    def test_missing_real_run_fails(self):
        self.raw['RNS_runs'].pop();self.assertRaisesRegex(ValueError,'TWO_RUNS',self.check)
    def test_failed_solver_fails(self):
        self.raw['RNS_runs'][0]['result']['status']='FAIL';self.assertRaisesRegex(ValueError,'SOLVER',self.check)
    def test_same_grid_binaries_fail(self):
        self.raw['RNS_runs'][1]['rns_binary_sha256']='a'*64;self.assertRaisesRegex(ValueError,'NOT_DISTINCT',self.check)
    def test_suspicious_mass_fails(self):
        self.raw['RNS_runs'][0]['result']['M_msun']=2.08;self.assertRaisesRegex(ValueError,'INVALID_GR',self.check)
    def test_suspicious_frequency_fails(self):
        self.raw['RNS_runs'][0]['result']['spin_hz']=300;self.assertRaisesRegex(ValueError,'INVALID_GR',self.check)
    def test_suspicious_radius_fails(self):
        self.raw['RNS_runs'][0]['result']['R_equatorial_km']=11
        self.raw['RNS_runs'][1]['result']['R_equatorial_km']=11.002
        self.assertRaisesRegex(ValueError,'UNEXPECTED_ROTATING',self.check)
    def test_grid_drift_fails(self):
        self.raw['RNS_runs'][1]['result']['R_equatorial_km']=12.57;self.assertRaisesRegex(ValueError,'SPATIAL_DIFFERENCE',self.check)
    def test_changed_model_fails(self):
        self.raw['model']='MPA1_NATIVE';self.assertRaisesRegex(ValueError,'MODEL_IDENTITY',self.check)
    def test_tov_provenance_fails(self):
        self.tov['source']['original_sources_modified']=True;self.assertRaisesRegex(ValueError,'TOV_MODIFIED',self.check)
    def test_rns_commit_mismatch_fails(self):
        self.raw['rns_source']['commit']='123';self.assertRaisesRegex(ValueError,'RNS_SOURCE_DRIFT',self.check)
    def test_source_byte_verification_is_fail_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'m.rns'
            file.write_text('tampered')
            with self.assertRaisesRegex(ValueError,'BYTE_DRIFT'):
                f.validate(self.raw,self.tov,rns_table_path=file,enforce_sha=True)

if __name__=='__main__':unittest.main()
