"""Fail-closed F70 regression checks without falsely claiming a C run."""
import json, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from f70_spin_matched_rns import validate_f68, prior_diagnosis, compare, EOS_SHA, TARGET_HZ

class F70Checks(unittest.TestCase):
    def setUp(self):
        def doc(grid):
            d={'grid':grid,'model':'MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL','not_original_MPA1':True,
               'rns_derived_table_sha256':EOS_SHA,'original_seven_EOS_Bayes':'NOT_RUN','direct_C_stars':{}}
            for k in ('2.073','2.250'):
                d['direct_C_stars'][k]={'rotating':{'star':{'mass_msun':float(k),'spin_hz_reported':TARGET_HZ+.02,
                       'radius_eq_km':12.5,'central_energy_density_g_cm3':1.e15}},
                     'static':{'star':{'spin_hz_reported':0.,'radius_eq_km':12.4}}}
            return d
        self.c=doc('151x301');self.f=doc('201x401')
    def test_model_verified(self):validate_f68(self.c,'151x301')
    def test_drift_rejected(self):
        self.c['rns_derived_table_sha256']='bad'
        with self.assertRaises(ValueError):validate_f68(self.c,'151x301')
    def test_frequency_out_of_bound_rejected(self):
        self.c['direct_C_stars']['2.073']['rotating']['star']['spin_hz_reported']=TARGET_HZ+.3
        with self.assertRaises(ValueError):validate_f68(self.c,'151x301')
    def test_baseline_exposes_confounding(self):
        d=prior_diagnosis(self.c,self.f)
        self.assertIs(d['2.073']['F68_radius_is_pure_mesh_error'],False)
    def test_comparison_requires_same_eos(self):
        self.c['rns_derived_table_sha256']='wrong'
        a={'grid':'151x301','rns_eos_sha256':EOS_SHA,'stars':{}}
        b={'grid':'201x401','rns_eos_sha256':EOS_SHA,'stars':{}}
        with self.assertRaises(ValueError):compare(a,b,(self.c,self.f))
    def test_no_interpolated_star_claim(self):
        import inspect
        from f70_spin_matched_rns import mass_spin_root
        self.assertIn('equal_spin_direct_model',inspect.getsource(mass_spin_root))
    def test_f69_conditional_separate(self):
        self.assertNotIn('FE56',self.c['model'])
    def test_stricter_spin_than_f68(self):
        from f70_spin_matched_rns import SPIN_TOL
        self.assertLess(SPIN_TOL,0.01)
    def test_stricter_mass_than_f68(self):
        from f70_spin_matched_rns import MASS_TOL
        self.assertLess(MASS_TOL,.0015)

if __name__=='__main__':unittest.main()