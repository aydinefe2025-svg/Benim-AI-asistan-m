"""F89 mocked regressions are not observational or real Einstein/C results."""
import math,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f89_fixed_j_real_rns import FACTORS,check_star,root_at_fixed_j,solve_grid
RHO=1.742e15
J=4.83e48
F=345.0

def fake(logrho,f,sign=1):
    rho=10**logrho;x=rho/RHO-1
    target_f=F+80*x
    return {'M_msun':2.073+sign*.15*x,'spin_hz':f,
            'R_equatorial_km':10.8,'J_cgs':J*f/target_f,
            'rho_c_g_cm3':rho,'real_C_solver':True}

class F89RootTests(unittest.TestCase):
    def setUp(self):
        self.base={**fake(math.log10(RHO),F),'commanded_f_hz':F}
    def test_five_sample_fixed_J_positive_slope(self):
        x=solve_grid(lambda lr,f:fake(lr,f),self.base,1.83e15,real_required=False)
        self.assertTrue(x['mass_strict_increasing'])
        self.assertEqual([p['fractional_rho_change'] for p in x['points']],list(FACTORS))
        self.assertAlmostEqual(x['central_slope_Msun_per_relative_rho'],.15,places=6)
        for p in x['points']:self.assertLessEqual(p['J_relative_error'],3e-5)
    def test_rejects_negative_slope_not_stable_claim(self):
        b={**fake(math.log10(RHO),F,-1),'commanded_f_hz':F}
        y=solve_grid(lambda lr,f:fake(lr,f,-1),b,1.83e15,real_required=False)
        self.assertFalse(y['mass_strict_increasing'])
        self.assertEqual(y['dynamical_stability'],'NOT_DEMONSTRATED')
        self.assertIn('NEGATIVE_OR_MIXED',y['local_interpretation'])
    def test_rejects_acausal_sample(self):
        with self.assertRaisesRegex(ValueError,'ACAUSAL'):
            solve_grid(lambda lr,f:fake(lr,f),self.base,1.78e15,real_required=False)
    def test_rejects_wrong_baseline_J(self):
        with self.assertRaisesRegex(ValueError,'BASELINE_NOT_REPRODUCIBLE'):
            solve_grid(lambda lr,f:fake(lr,f),{**self.base,'J_cgs':5.05e48},
                       1.83e15,real_required=False)
    def test_rejects_synthetic_in_production(self):
        star=fake(math.log10(RHO),F);star.pop('real_C_solver')
        with self.assertRaisesRegex(ValueError,'SYNTHETIC_STAR_REJECTED'):
            check_star(star,RHO,real_required=True)
    def test_rejects_unbracketable_J(self):
        def no_j(lr,f):
            x=fake(lr,f);x['J_cgs']=J*2;return x
        with self.assertRaisesRegex(RuntimeError,'NOT_BRACKETED'):
            root_at_fixed_j(no_j,RHO,F,J,1.83e15,real_required=False)
    def test_rejects_wrong_density_from_solver(self):
        def wrong(lr,f):
            x=fake(lr,f);x['rho_c_g_cm3']*=1.05;return x
        with self.assertRaisesRegex(ValueError,'CENTRAL_DENSITY'):
            root_at_fixed_j(wrong,RHO,F,J,1.83e15,real_required=False)
if __name__=='__main__':unittest.main()
