import unittest
from target_mass_rns import bracketed_rotating_mass_solver

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

if __name__=='__main__':unittest.main()
