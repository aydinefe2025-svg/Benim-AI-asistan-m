import unittest,numpy as np
from rns_boundary_patch import (patch_source,START_P,START_H,bounded_h_from_p,bounded_p_from_h)


def simple():
    rho=np.geomspace(1e10,1e16,196)
    p=np.geomspace(1e27,1e35,196)
    h=np.linspace(1,1e19,196)
    n=np.geomspace(1e30,1e36,196)
    return np.column_stack((rho,p,h,n))

class CBoundaryPatch(unittest.TestCase):
    def test_patch_exact_code_both_hydro_functions(self):
        inp='HEADER\n'+START_P+'\n'+START_H+'\n'
        out=patch_source(inp)
        self.assertEqual(out.count('J0740 bounded first EOS bin'),2)
        self.assertNotIn(START_P,out)
    def test_double_patch_is_refused(self):
        src=patch_source(START_P+'\n'+START_H)
        with self.assertRaisesRegex(ValueError,'absent'):
            patch_source(src)
    def test_p_h_inverse_in_first_bin(self):
        a=simple();p=np.geomspace(a[0,1],a[1,1],30)
        for pp in p:
            hh=bounded_h_from_p(a,pp)
            pb=bounded_p_from_h(a,hh)
            self.assertLess(abs(pb/pp-1),2e-12)
    def test_no_pressure_extrapolation(self):
        a=simple()
        with self.assertRaisesRegex(ValueError,'Outside'):
            bounded_h_from_p(a,a[2,1])
    def test_no_H_extrapolation(self):
        a=simple()
        with self.assertRaisesRegex(ValueError,'Outside'):
            bounded_p_from_h(a,a[2,2])
    def test_nonmonotone_H_rejected(self):
        a=simple();a[13,2]=a[12,2]
        with self.assertRaisesRegex(ValueError,'Invalid'):
            bounded_h_from_p(a,1e27)
    def test_patch_requires_exact_pinned_source(self):
        with self.assertRaises(ValueError):patch_source('not the original RNS equil source')

if __name__=='__main__':unittest.main()
