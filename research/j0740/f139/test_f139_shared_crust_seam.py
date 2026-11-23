"""Regression tests: real production seam, mock external LAL boundary only."""
import io, json, os, sys, tempfile, unittest, zipfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f139_shared_crust_seam import source_gate, probe_model, compare_seam, check_original_star_reachability

class FakeEOS:
    def __init__(self, name):self.name=name

class FakeLAL:
    def SimNeutronStarEOSByName(self,name):return FakeEOS(name)
    def SimNeutronStarEOSEnergyDensityDerivOfPressureGeometerized(self,p,eos):
        # The negative derivative is finite only over a bounded native pressure region.
        return -3. if (eos.name!='APR4_EPP' and 2.0 < p < 2.4) else 5.
    def SimNeutronStarEOSEnergyDensityOfPressureGeometerized(self,p,eos):return p*2.+100.

class Tests(unittest.TestCase):
    def test_01_source_gate_rejects_tampered_npz(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'ENG.npz'
            np.savez(src,p=np.linspace(1,4,10),e=np.linspace(100,200,10),cs2=np.ones(10),eos_name='ENG',source='LALSimulation')
            with self.assertRaisesRegex(ValueError,'SOURCE_SHA_MISMATCH'):
                source_gate(src,'ENG')

    def test_02_probe_seam_reports_native_finite_negative_width_and_preserves_samples(self):
        p=np.linspace(1.,4.,301)
        e=np.linspace(100.,200.,301)
        observed,rows=probe_model(FakeLAL(), 'ENG',p,e, step=100, neighbors=2, per_interval=51)
        self.assertEqual(observed['native_calls'],201)
        self.assertTrue(observed['negative_cs2_sample_count']>0)
        self.assertTrue(observed['native_negative_pressure_span_exists'])
        self.assertTrue(any(row['cs2']<0 for row in rows))
        self.assertEqual(len(rows),observed['native_calls'])

    def test_03_positive_source_stays_positive(self):
        p=np.linspace(1.,4.,301);e=np.linspace(100.,200.,301)
        observed,rows=probe_model(FakeLAL(),'APR4_EPP',p,e,step=100,neighbors=2,per_interval=51)
        self.assertEqual(observed['negative_cs2_sample_count'],0)
        self.assertFalse(observed['native_negative_pressure_span_exists'])

    def test_04_missing_native_lal_api_fails_closed(self):
        class BadLAL:pass
        with self.assertRaisesRegex(RuntimeError,'LAL_NATIVE_API_MISSING'):
            probe_model(BadLAL(),'ENG',np.arange(301.)+1,np.arange(301.)+100,100,2,51)

    def test_05_nonascending_source_is_rejected(self):
        p=np.linspace(1.,4.,301);p[100]=p[99]
        with self.assertRaisesRegex(ValueError,'INVALID_SOURCE_PRESSURE'):
            probe_model(FakeLAL(),'ENG',p,np.linspace(100.,200.,301),100,2,51)

    def test_06_common_seam_identifies_shared_knot_between_models(self):
        p=np.linspace(1.,4.,301);e=np.linspace(100.,200.,301)
        a=compare_seam({'ENG':(p,e),'MPA1':(p.copy(),e.copy()),'APR4_EPP':(p.copy(),e*1.01)},100)
        self.assertTrue(a['ENG__MPA1']['common_pressure_knot'])
        self.assertTrue(a['ENG__MPA1']['same_energy_to_1e-7'])
        self.assertFalse(a['APR4_EPP__ENG']['same_energy_to_1e-7'])

    def test_07_source_central_density_reachability_is_physical_and_fail_closed(self):
        record={'mass_msun':2.0712,'central_density_g_cm3':1.75e15,
                'original_npz_sha256':'refsha','n_original_C_stars':42}
        p=np.array([1.,2.,3.]);e=np.array([1e-13,2e-13,3e-13]);
        self.assertTrue(check_original_star_reachability(record,'refsha',e[1])['seam_inside_star_density_range'])
        with self.assertRaisesRegex(ValueError,'STAR_REFERENCE_EOS_SHA_MISMATCH'):
            check_original_star_reachability(record,'wrong',e[1])
        with self.assertRaisesRegex(ValueError,'STAR_CENTER_NOT_REACHING_SEAM'):
            check_original_star_reachability({**record,'central_density_g_cm3':1e10},'refsha',e[1])

if __name__=='__main__':unittest.main()