import unittest
import numpy as np
from j0740_absolute_enthalpy_gr import absolute_pseudoenthalpy_rows,compare_at_same_center,C2_CGS,audit


def example():
    p=np.geomspace(1e26,1e35,196)
    rho=p/((29979245800.)**2*.4)
    h=np.linspace(1,1e18,196)
    n=np.linspace(1e20,1e31,196)
    return np.column_stack((rho,p,h,n))

class AbsoluteH(unittest.TestCase):
    def test_restore_original_pseudoenthalpy(self):
        a=example();h0=.0020411780879532634
        b=absolute_pseudoenthalpy_rows(a,h0)
        self.assertAlmostEqual(b[0,2]/C2_CGS,h0,places=13)
        self.assertTrue(np.array_equal(b[:,0],a[:,0]))
        self.assertTrue(np.array_equal(b[:,1],a[:,1]))
        self.assertTrue(np.array_equal(b[:,3],a[:,3]))
    def test_no_double_enthalpy_restoration(self):
        a=example();b=absolute_pseudoenthalpy_rows(a,.002)
        with self.assertRaisesRegex(ValueError,'legacy H'):
            absolute_pseudoenthalpy_rows(b,.002)
    def test_zero_h0_rejected(self):
        with self.assertRaisesRegex(ValueError,'positive'):
            absolute_pseudoenthalpy_rows(example(),0)
    def test_nonmonotone_h_rejected(self):
        a=example();a[15,2]=a[14,2]
        with self.assertRaisesRegex(ValueError,'positive'):
            absolute_pseudoenthalpy_rows(a,.002)
    def test_bad_shape_rejected(self):
        with self.assertRaises(ValueError):
            absolute_pseudoenthalpy_rows(np.ones((196,3)),.002)
    def test_fixed_center_comparison(self):
        old=dict(mass_msun=2.07,radius_eq_km=12.0,central_energy_density_g_cm3=1e15)
        new=dict(mass_msun=2.08,radius_eq_km=12.05,central_energy_density_g_cm3=1e15)
        x=compare_at_same_center(old,new)
        self.assertAlmostEqual(x['delta_gr_radius_eq_km'],.05)
        self.assertAlmostEqual(x['delta_gr_mass_msun'],.01)
    def test_fixed_center_guard(self):
        old=dict(mass_msun=2.07,radius_eq_km=12.0,central_energy_density_g_cm3=1e15)
        new=dict(mass_msun=2.08,radius_eq_km=12.05,central_energy_density_g_cm3=1.5e15)
        with self.assertRaisesRegex(ValueError,'different'):
            compare_at_same_center(old,new)
    def test_no_unvalidated_gr(self):
        with self.assertRaisesRegex(ValueError,'identity'):
            audit({'status':'NOT_RUN'},None,None,None)

if __name__=='__main__':unittest.main()
