import math, tempfile, unittest
import numpy as np
from apr4_firstlaw_crust import FirstLawCrust,pchip_slopes

class TestFirstLawCrust(unittest.TestCase):
    def setUp(self):
        p=np.geomspace(1e-8,1e-3,31)
        e=1e-4*(p/1e-8)**.75
        self.p=p;self.e=e;self.n=e/1e-53;self.h=np.linspace(.01,.2,31)
        self.obj=FirstLawCrust(p,e,self.n,self.h,float(e[24]))

    def test_low_p_polytrope_exact_h(self):
        q=self.obj.at_p(1e-11);p=q['p'];e=q['e'];b=self.obj.beta
        self.assertAlmostEqual(q['h'],math.log1p(p/e)/(1-b),delta=1e-12)
        self.assertGreater(q['n'],0)

    def test_firstlaw_derivative_nh_same_eos(self):
        p=float(self.p[13]);dx=1e-5
        a=self.obj.at_p(p*math.exp(-dx));b=self.obj.at_p(p*math.exp(dx));v=self.obj.at_p(p)
        dn=(math.log(b['n'])-math.log(a['n']))/(2*dx)
        dh=(b['h']-a['h'])/(2*dx)
        dnp=v['s']*v['e']/(v['e']+p)
        dhp=p/(v['e']+p)
        self.assertAlmostEqual(dn,dnp,delta=2e-7)
        self.assertAlmostEqual(dh,dhp,delta=2e-7)

    def test_c1_pressure_energy_at_join(self):
        p0=self.obj.p0
        l=self.obj.at_p(p0*(1-1e-9));r=self.obj.at_p(p0*(1+1e-9))
        self.assertAlmostEqual(l['e']/r['e'],1,delta=1e-7)
        self.assertAlmostEqual(l['s'],r['s'],delta=1e-7)
        self.assertAlmostEqual(l['h'],r['h'],delta=1e-7)
        self.assertAlmostEqual(l['n']/r['n'],1,delta=1e-7)

    def test_n_column_ablation_other_columns_bit_identical(self):
        rows,n0,states=self.obj.make_table(float(self.p[22]),points=196)
        self.assertTrue(np.array_equal(rows[:,:3],n0[:,:3]))
        self.assertFalse(np.array_equal(rows[:,3],n0[:,3]))
        self.assertLess(np.max(np.abs(rows[:,3]/n0[:,3]-1)),1)

    def test_reject_source_nonmonotone(self):
        ee=self.e.copy();ee[5]=ee[4]*.999
        with self.assertRaises(ValueError):FirstLawCrust(self.p,ee,self.n,self.h,float(self.e[24]))

    def test_reject_invalid_low_pressure_exponent(self):
        ee=1e-3*(self.p/self.p[0])**1.3
        with self.assertRaises(ValueError):FirstLawCrust(self.p,ee,ee/1e-53,self.h,float(ee[24]))

    def test_reject_inconsistent_n_source(self):
        n=self.n.copy();n[3]*=1.01
        with self.assertRaises(ValueError):FirstLawCrust(self.p,self.e,n,self.h,float(self.e[24]))

    def test_reject_out_of_range_no_untrusted_extrapolation(self):
        with self.assertRaises(ValueError):self.obj.at_p(float(self.p[-1]*2))
        with self.assertRaises(ValueError):self.obj.make_table(self.p[-1],points=201)

if __name__=='__main__':unittest.main()
