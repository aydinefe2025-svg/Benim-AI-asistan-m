import unittest
import numpy as np
from target_mass_rns import bracketed_rotating_mass_solver, source_fit_valid_branch, fixed_gravitational_mass_radius_difference

class TestGRMassRoot(unittest.TestCase):
    def test_target_gravitational_mass_is_solved(self):
        def fake_rns(ec):
            mass=2.03+(ec-1e15)*(0.20/0.4e15)
            return {'central_energy_density_g_cm3':ec,'mass_msun':mass,'radius_eq_km':12.60}
        result,trace=bracketed_rotating_mass_solver(fake_rns,2.073,1e15,1.4e15)
        self.assertLessEqual(abs(result['mass_msun']-2.073),0.0015)
        self.assertLess(len(trace),22)
    def test_unbracketed_mass_fails_not_extrapolates(self):
        def fake(ec):return {'mass_msun':1.1,'radius_eq_km':12}
        with self.assertRaisesRegex(ValueError,'not bracketed'):
            bracketed_rotating_mass_solver(fake,2.073,1e15,1.4e15)
    def test_unstable_mass_branch_fails_not_silently_monotone(self):
        def fake(ec):
            m=1.9+(ec-1e15)*(0.6/0.4e15)
            if ec==1.2e15: m=3.0
            return {'mass_msun':m,'radius_eq_km':12}
        with self.assertRaisesRegex(ValueError,'nonmonotone'):
            bracketed_rotating_mass_solver(fake,2.073,1e15,1.4e15)


class TestSemiEmpiricalSourceDomain(unittest.TestCase):
    def test_low_mass_giant_radius_nodes_are_excluded_without_interpolation(self):
        m=np.array([0.095,0.11,0.50,1.50,2.00,2.20])
        r=np.array([156.0,40.0,13.0,12.5,12.4,12.3])
        valid_m,valid_r,details=source_fit_valid_branch(m,r,346.536369)
        self.assertEqual(details['excluded_low_mass_nodes_outside_fit_domain'],2)
        np.testing.assert_array_equal(valid_m,m[2:])
        np.testing.assert_array_equal(valid_r,r[2:])
        self.assertLess(details['fit_valid_mass_min_msun'],2.073)

    def test_does_not_cut_already_valid_curve(self):
        m=np.array([1.5,1.8,2.0,2.2])
        r=np.array([12.6,12.5,12.4,12.3])
        a,b,d=source_fit_valid_branch(m,r,346.536369)
        self.assertEqual(d['excluded_low_mass_nodes_outside_fit_domain'],0)
        np.testing.assert_array_equal(a,m)

    def test_noncontiguous_valid_domain_is_rejected(self):
        m=np.array([0.1,0.5,1.1,1.4,2.0,2.3])
        r=np.array([156,13,12,100,12.4,12.3])
        with self.assertRaisesRegex(ValueError,'not a contiguous'):
            source_fit_valid_branch(m,r,346.536369)

    def test_all_out_of_domain_fails(self):
        with self.assertRaisesRegex(ValueError,'Too few'):
            source_fit_valid_branch(np.array([.1,.15,.2]),np.array([160,170,180]),346.536369)


class TestFixedGravitationalMassComparison(unittest.TestCase):
    def test_radius_difference_only_at_same_gravitational_mass(self):
        rotating={'mass_msun':2.073,'radius_eq_km':12.53}
        static={'mass_msun':2.073,'radius_eq_km':12.44}
        self.assertAlmostEqual(fixed_gravitational_mass_radius_difference(rotating,static,2.073),0.09)

    def test_mismatch_rejected_even_if_radius_increases(self):
        rotating={'mass_msun':2.073,'radius_eq_km':12.53}
        static={'mass_msun':2.052,'radius_eq_km':12.42}
        with self.assertRaisesRegex(ValueError,'not validated'):
            fixed_gravitational_mass_radius_difference(rotating,static,2.073)

    def test_bad_radius_order_rejected(self):
        rotating={'mass_msun':2.073,'radius_eq_km':12.4}
        static={'mass_msun':2.073,'radius_eq_km':12.5}
        with self.assertRaisesRegex(ValueError,'not validated'):
            fixed_gravitational_mass_radius_difference(rotating,static,2.073)

if __name__=='__main__':unittest.main()
