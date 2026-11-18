"""F55 numerical and provenance guardrails (synthetic data are not RNS stars)."""
import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import f55_wff1_eos_knot_sensitivity as f55

def thermo(points=60):
    rho=np.geomspace(1e12,1e15,points)
    p=.5*rho*(f55.C*100)**2
    h=np.linspace(.01,.02,points)
    egeo=rho*f55.G*1e3/f55.C**2
    pgeo=p*f55.G/(f55.C**4*10)
    n=(egeo+pgeo)*np.exp(-h)*f55.C**2/(f55.G*f55.MB)/1e6
    return np.column_stack([rho,p,h*(f55.C*100)**2,n])

def match(mextra=0,radius_delta=0,badJ=0,monotonic=False):
    data={}
    for knots in f55.VARIANT_KNOTS:
        rows=[]
        for i,rho in enumerate(f55.MATCHED_E15):
            peak=(-.0001 if i!=1 else 0)
            mass=2.11+peak+mextra+(i*.0001 if monotonic else 0)
            rows.append({'status':'DIRECT_C_FIXED_J_PASS','density_e15':rho,
                         'variant':{'mass_msun':mass,'relative_J_residual':badJ},
                         'delta_mass_msun':mextra,'delta_radius_km':radius_delta})
        data[str(knots)]={'matched_rows':rows}
    return data

class F55Tests(unittest.TestCase):
    def test_thermo_positive_causal_firstlaw(self):
        result=f55.table_thermodynamic_diagnostic(thermo())
        self.assertEqual(result['rows'],60)
        self.assertAlmostEqual(result['max_secant_dp_de'],.5,places=8)
        self.assertLess(result['firstlaw_n_max_rel_error'],1e-13)

    def test_causality_rejection(self):
        rows=thermo();rows[:,1]*=3
        with self.assertRaisesRegex(ValueError,'CAUSALITY'):
            f55.table_thermodynamic_diagnostic(rows)

    def test_firstlaw_baryon_column_rejection(self):
        rows=thermo();rows[:,3]*=1.04
        with self.assertRaisesRegex(ValueError,'FIRSTLAW'):
            f55.table_thermodynamic_diagnostic(rows)

    def test_nonmonotonic_table_rejected(self):
        rows=thermo();rows[5,0]=rows[4,0]
        with self.assertRaisesRegex(ValueError,'NONPOSITIVE_OR_NONMONOTONE'):
            f55.table_thermodynamic_diagnostic(rows)

    def test_three_variants_valid_and_not_physical(self):
        s=f55.summarize_variants(match())
        self.assertEqual(s['status'],'PASS_THREE_EOS_KNOT_SENSITIVITIES_NOT_PHYSICAL_EOS')
        self.assertFalse(s['EOS_physics_validated'])
        self.assertEqual(s['global_dynamical_stability'],'NOT_ESTABLISHED')

    def test_mass_radius_threshold_fail_closed(self):
        self.assertEqual(f55.summarize_variants(match(mextra=.014))['status'],
                         'PARTIAL_OR_FAILED_CANDIDATE_KNOT_SENSITIVITY')
        self.assertEqual(f55.summarize_variants(match(radius_delta=.16))['status'],
                         'PARTIAL_OR_FAILED_CANDIDATE_KNOT_SENSITIVITY')

    def test_J_tolerance_and_peak_fail_closed(self):
        self.assertEqual(f55.summarize_variants(match(badJ=.01))['status'],
                         'PARTIAL_OR_FAILED_CANDIDATE_KNOT_SENSITIVITY')
        self.assertEqual(f55.summarize_variants(match(monotonic=True))['status'],
                         'PARTIAL_OR_FAILED_CANDIDATE_KNOT_SENSITIVITY')

    def test_one_failed_root_not_mislabeled_success(self):
        x=match();x['196']['matched_rows'][0]['status']='DIRECT_C_VARIANT_FAILED'
        self.assertEqual(f55.summarize_variants(x)['per_variant']['196']['status'],
                         'INCOMPLETE_DIRECT_C_VARIANT')

if __name__=='__main__':
    unittest.main()
