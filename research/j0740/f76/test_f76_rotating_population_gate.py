import unittest
import numpy as np
from f76_rotating_population_gate import classify_one_star

class SourceKnotGates(unittest.TestCase):
    def setUp(self):
        self.d=np.geomspace(1e10,1e16,100)
        self.cs=np.linspace(.1,.9,100)
    def test_pass_never_calls_it_physical_cert(self):
        r=classify_one_star(self.d,self.cs,1e15)
        self.assertEqual(r['status'],'PASS_KNOTS_ONLY_UNCERTIFIED')
    def test_negative_at_crust_invalidates_even_large_core(self):
        v=self.cs.copy();v[2]=-.00001
        self.assertEqual(classify_one_star(self.d,v,1e15)['status'],'SOURCE_KNOT_CAUSALITY_VIOLATED')
    def test_superluminal_at_core_invalidates(self):
        v=self.cs.copy();v[55]=1.00001
        self.assertEqual(classify_one_star(self.d,v,1e15)['superluminal_source_knots_below_core'],1)
    def test_superluminal_above_core_does_not_invalidate_star_sample(self):
        v=self.cs.copy();v[99]=1.01
        self.assertEqual(classify_one_star(self.d,v,1e15)['status'],'PASS_KNOTS_ONLY_UNCERTIFIED')
    def test_exact_at_central_density_is_counted(self):
        v=self.cs.copy();v[60]=-0.2
        self.assertEqual(classify_one_star(self.d,v,float(self.d[60]))['negative_source_knots_below_core'],1)
    def test_outside_source_table_does_not_pass(self):
        self.assertEqual(classify_one_star(self.d,self.cs,1e17)['status'],'UNRESOLVED_OUTSIDE_SOURCE_TABLE')
    def test_outside_source_table_with_violation_still_fails(self):
        v=self.cs.copy();v[30]=-0.4
        self.assertEqual(classify_one_star(self.d,v,1e17)['status'],'SOURCE_KNOT_CAUSALITY_VIOLATED')
    def test_no_points_before_center_rejected(self):
        with self.assertRaises(ValueError):classify_one_star(self.d,self.cs,1e9)
    def test_nonmonotone_energy_edge_is_physical_failure(self):
        d=self.d.copy();d[4]=d[3]-1
        r=classify_one_star(d,self.cs,1e15)
        self.assertEqual(r['status'],'SOURCE_KNOT_CAUSALITY_VIOLATED')
        self.assertEqual(r['nonmonotone_source_energy_edges_below_core'],1)
    def test_nonfinite_cs_rejected(self):
        c=self.cs.copy();c[0]=float('nan')
        with self.assertRaises(ValueError):classify_one_star(self.d,c,1e15)
    def test_zero_cs2_is_admissible_knot_value(self):
        c=self.cs.copy();c[0]=0
        self.assertEqual(classify_one_star(self.d,c,1e15)['status'],'PASS_KNOTS_ONLY_UNCERTIFIED')
    def test_one_cs2_is_admissible_knot_value(self):
        c=self.cs.copy();c[0]=1
        self.assertEqual(classify_one_star(self.d,c,1e15)['status'],'PASS_KNOTS_ONLY_UNCERTIFIED')

if __name__=='__main__': unittest.main()