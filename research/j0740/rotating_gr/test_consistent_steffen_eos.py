import unittest
import numpy as np
from consistent_eos import ConsistentEOS

class ConsistentSteffenEOS(unittest.TestCase):
    def setUp(self):
        self.p=np.geomspace(1e-12,1e-8,9)
        self.e=1e-8*(self.p/self.p[0])**0.5
        self.raw=np.column_stack([self.p,self.e])

    def test_source_knots_and_derived_thermodynamics_are_monotone(self):
        eos=ConsistentEOS(self.raw,subdivisions=8)
        rows=eos.rns_rows(subdivisions=2)
        self.assertTrue(np.all(np.diff(rows,axis=0)>0))
        self.assertTrue(np.all(np.isfinite(rows)))

    def test_causal_derivative_and_first_causal_limit(self):
        eos=ConsistentEOS(self.raw)
        self.assertTrue(all(v>0 for v,_ in eos.extrema()))
        pressure,causal=eos.causal_pressure_limit()
        self.assertTrue(causal)
        self.assertAlmostEqual(pressure,self.p[-1],places=18)

    def test_low_pressure_gas_continuation_is_positive_and_causal(self):
        eos=ConsistentEOS(self.raw)
        for p in np.geomspace(self.p[0]*1e-8,self.p[0],20):
            self.assertGreater(float(eos.energy(p)),0.)
            self.assertGreater(eos.cs2(float(p)),0.)
            self.assertLess(eos.cs2(float(p)),1.)
            self.assertGreater(eos.h(float(p)),0.)

    def test_enthalpy_and_pressure_maps_roundtrip(self):
        eos=ConsistentEOS(self.raw,subdivisions=32)
        for p in np.geomspace(self.p[0]*1e-8,self.p[-1],50):
            h=eos.h(float(p));back=eos.pressure(h)
            self.assertLess(abs(back/p-1.),2e-4)

    def test_nonmonotone_source_knots_rejected_without_reordering(self):
        bad=self.raw.copy();bad[4,1]=bad[3,1]*.9
        with self.assertRaisesRegex(ValueError,'Strictly increasing'):
            ConsistentEOS(bad)

    def test_causal_cut_keeps_original_spline_and_cannot_reenter_acausal_branch(self):
        p=np.geomspace(1.,1000.,13);e=10.*np.sqrt(p)
        full=ConsistentEOS(np.column_stack([p,e]),subdivisions=12)
        cut_pressure,through_end=full.causal_pressure_limit()
        self.assertFalse(through_end)
        cut=ConsistentEOS(np.column_stack([p,e]),subdivisions=12,max_pressure=cut_pressure)
        self.assertLessEqual(max(v for v,_ in cut.extrema()),1.+2e-10)
        trial=np.geomspace(p[0],cut_pressure*.999,20)
        np.testing.assert_allclose(cut.energy(trial),full.energy(trial),rtol=1e-13,atol=0)
        self.assertAlmostEqual(cut.pmax,cut_pressure,places=12)
        with self.assertRaisesRegex(ValueError,'exceeds declared EOS support'):
            cut.energy(cut_pressure*1.001)

if __name__=='__main__': unittest.main()

