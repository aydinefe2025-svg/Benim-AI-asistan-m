"""F82 new real-data acceptance gates; synthetic source examples are NOT GR results."""
from __future__ import annotations
import sys, math, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import f82_bps_mpa1_real_fixed_j as F

class PhysicsGates(unittest.TestCase):
    def stars(self, masses=(1.8,2.2,2.45,2.40,2.30), ec=(1.,1.4,1.7,2.,2.3)):
        return [{'status':'DIRECT_C_FIXED_J_NUMERICAL_PASS_NOT_STABILITY_CERTIFICATE',
                 'mass_msun':m,'ec_g_cm3':e*1e15,'radius_eq_km':12.5,'spin_hz':345.,
                 'relative_J_residual':0.,'axis_ratio':.98} for m,e in zip(masses,ec)]
    def test_01_predeclared_J_is_F81_source_J(self):
        self.assertEqual(F.J_REFERENCE,6.065849263583e48)
        self.assertEqual(F.EOS_SHA,'f4a183661962acdddc7aebde3830116578feb6fba88a1a68c9fd57a993058675')
        self.assertEqual(F.F81_RESULT_SHA,'36d726706f8aadcbae416693dc4f682c890defe9ca896b76641655140aede620')
    def test_02_peak_bracketing_real_signed_slope(self):
        x=F.peak_summary(self.stars(),min_success=5)
        self.assertTrue(x['status'].startswith('SAMPLED_'))
        self.assertEqual(x['peak_density_g_cm3'],1.7e15)
        self.assertEqual(x['global_dynamic_stability'],'NOT_ESTABLISHED')
    def test_03_monotone_curve_refused(self):
        x=F.peak_summary(self.stars([1.7,1.9,2.1,2.3,2.5]),min_success=5)
        self.assertEqual(x['status'],'NO_SAMPLED_CONSTANT_J_TURNOVER')
    def test_04_peak_at_high_edge_refused(self):
        x=F.peak_summary(self.stars([2.5,2.3,2.0,1.9,1.7]),min_success=5)
        self.assertEqual(x['status'],'NO_SAMPLED_CONSTANT_J_TURNOVER')
    def test_05_insufficient_physical_solver_rows_refused(self):
        x=F.peak_summary(self.stars()[:3],min_success=5)
        self.assertEqual(x['status'],'INSUFFICIENT_REAL_C_CONSTANT_J_STARS')
    def test_06_failed_rows_never_fake_peak(self):
        rows=self.stars()[:3]+[{'status':'REJECTED_REAL_C_ROOT','ec_g_cm3':1.6e15,'mass_msun':200.}]+self.stars()[3:]
        x=F.peak_summary(rows,min_success=5)
        self.assertTrue(x['status'].startswith('SAMPLED_'))
        self.assertEqual(x['peak_M_msun'],2.45)  # failed 200 Msun row cannot drive the peak
    def test_07_same_density_two_mesh_difference(self):
        a=self.stars();b=[dict(x,radius_eq_km=x['radius_eq_km']-.0004,mass_msun=x['mass_msun']-.0003) for x in a]
        z=F.compare_grids(a,b)
        self.assertEqual(z['count'],5)
        self.assertAlmostEqual(z['max_abs_mass_msun'],.0003)
        self.assertAlmostEqual(z['max_abs_radius_m'],.4)
    def test_08_not_same_density_refused_for_pair(self):
        a=self.stars();b=[dict(x,ec_g_cm3=x['ec_g_cm3']+10.) for x in a]
        z=F.compare_grids(a,b)
        self.assertEqual(z['count'],0)
    def test_09_wrong_J_residual_rejected(self):
        a=self.stars();b=self.stars();b[0]['relative_J_residual']=.002
        with self.assertRaisesRegex(ValueError,'F82_J_CONSTRAINT_MISMATCH'):
            F.compare_grids(a,b)
    def test_10_hard_limits_never_claim_dynamic_stability(self):
        x=F.peak_summary(self.stars(),min_success=5)
        self.assertNotIn('DYNAMIC_STABILITY_CERTIFIED',str(x))
    def test_11_reject_fake_end_point_fitted_peak(self):
        for masses in ([1.,1.5,1.5,1.3,1.2],[1.,1.5,2.,2.5,3.]):
            self.assertEqual(F.peak_summary(self.stars(masses),min_success=5)['status'],'NO_SAMPLED_CONSTANT_J_TURNOVER')
    def test_12_source_validation_wrong_hash_rejected(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as t:
            e=Path(t)/'eos';e.write_text('fake')
            f=Path(t)/'f81';f.write_text('fake')
            b=Path(t)/'binary';b.write_text('fake')
            with self.assertRaisesRegex(ValueError,'F82_ARCHIVED_F81_OR_EOS_BYTES_DRIFT'):
                F.validate_source(f,e,{g:b for g in F.GRIDS})

if __name__=='__main__':unittest.main()
