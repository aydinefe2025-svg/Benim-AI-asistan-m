import unittest
import numpy as np
from center_causality import central_causality, audit, CONVERT

class CenterCausalityTests(unittest.TestCase):
    def example(self):
        rho=np.linspace(1e12,2e15,400)
        e=rho/CONVERT
        p=np.linspace(1e-14,1e-9,400)
        cs2=np.linspace(.08,.9,400)
        return e,p,cs2

    def test_center_interpolation_same_source_bracket(self):
        e,p,cs2=self.example()
        out=central_causality(e,p,cs2,1.4e15)
        self.assertLess(abs(out["cs2_over_c2_interpolated_linear_energy"]-np.interp(1.4e15,e*CONVERT,cs2)),1e-12)
        self.assertEqual(out["classification"],"NO_NEGATIVE_OR_SUPERLUMINAL_SOURCE_NODES_THROUGH_CENTER")

    def test_superluminal_node_within_star_is_explicit(self):
        e,p,cs2=self.example()
        cs2[-60:]=1.2
        out=central_causality(e,p,cs2,1.9e15)
        self.assertGreater(out["native_superluminal_nodes_below_center"],0)
        self.assertEqual(out["classification"],"SUPERLUMINAL_NATIVE_SOURCE_NODES_WITHIN_ROTATING_STAR")

    def test_superluminal_above_center_not_interior(self):
        e,p,cs2=self.example()
        cs2[-20:]=1.2
        out=central_causality(e,p,cs2,1.2e15)
        self.assertEqual(out["native_superluminal_nodes_below_center"],0)

    def test_negative_crust_node_never_clipped(self):
        e,p,cs2=self.example()
        cs2[3]=-0.17
        out=central_causality(e,p,cs2,1.2e15)
        self.assertEqual(out["native_negative_nodes_below_center"],1)
        self.assertLess(out["negative_source_node_cs2"][0],0)
        self.assertIn("NEGATIVE_CS2",out["classification"])

    def test_no_density_extrapolation(self):
        e,p,cs2=self.example()
        with self.assertRaisesRegex(ValueError,"outside"):
            central_causality(e,p,cs2,3e15)

    def test_low_energy_turnback_does_not_change_high_branch(self):
        e,p,cs2=self.example()
        e[2]=e[1]*.7
        out=central_causality(e,p,cs2,1.3e15)
        self.assertEqual(out["source_nonmonotone_energy_prefix_final_index"],2)

    def test_nonmonotonic_pressure_is_rejected(self):
        e,p,cs2=self.example()
        p[23]=p[22]
        with self.assertRaisesRegex(ValueError,"Invalid source"):
            central_causality(e,p,cs2,1.3e15)

    def test_only_validated_rns_runs_accepted(self):
        with self.assertRaisesRegex(ValueError,"identity"):
            audit({"status":"PARTIAL_NOT_FINAL"},None)

if __name__=="__main__":
    unittest.main()
