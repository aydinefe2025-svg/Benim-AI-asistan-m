"""Source-anchored tests; no simulation output promoted to a physical EOS."""
import copy
import json
import math
import unittest
from pathlib import Path

from crust_local_causal_projection import (
    LocalProjectionNotFeasible,
    project_local_five_nodes,
)

SOURCE = Path(__file__).resolve().parent / "fixtures" / "j0740_source_crust_5pt_pinned.json"


def source_nodes(name):
    blob = json.loads(SOURCE.read_text(encoding="utf-8"))
    return blob["models"][name]


class LocalCrustBridgeTests(unittest.TestCase):
    def test_real_mpa1_five_nodes_need_nonzero_small_adjustment(self):
        original = source_nodes("MPA1")
        snapshot = copy.deepcopy(original)
        out = project_local_five_nodes(original, cap=0.95)
        self.assertEqual(original, snapshot, "the source forensic data must remain unchanged")
        self.assertEqual(out["modified_source_indices"], [253, 254])
        self.assertEqual(out["scope"], "diagnostic_local_secants_only_not_physical_eos")
        self.assertEqual(out["source_e_geom"][0], out["candidate_e_geom"][0])
        self.assertEqual(out["source_e_geom"][3:], out["candidate_e_geom"][3:])
        self.assertTrue(all(0 < v <= .95 + 2e-10 for v in out["candidate_secant_cs2_over_c2"]))
        self.assertLess(out["maximum_relative_energy_adjustment"], 2e-4)
        self.assertGreater(out["maximum_relative_energy_adjustment"], 1e-4)
        self.assertLess(out["original_secant_cs2_over_c2"][1], 0)

    def test_six_real_sources_allow_bounded_diagnostic_but_are_not_repaired(self):
        for name in ["ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2"]:
            with self.subTest(name=name):
                o = project_local_five_nodes(source_nodes(name), cap=0.95)
                self.assertLess(o["original_secant_cs2_over_c2"][1], 0)
                self.assertTrue(all(0 < a <= 0.9500000002 for a in o["candidate_secant_cs2_over_c2"]))
                self.assertFalse(o["full_eos_physics_validated"])
                self.assertFalse(o["original_native_negative_derivative_removed"])

    def test_stricter_cap_needs_strictly_larger_adjustment(self):
        nodes = source_nodes("MPA1")
        a = project_local_five_nodes(nodes, 1.0)
        b = project_local_five_nodes(nodes, 0.95)
        c = project_local_five_nodes(nodes, 0.90)
        self.assertLess(a["absolute_energy_shift_each_geom"], b["absolute_energy_shift_each_geom"])
        self.assertLess(b["absolute_energy_shift_each_geom"], c["absolute_energy_shift_each_geom"])

    def test_invalid_pressure_sequence_fails_closed(self):
        nodes = source_nodes("ENG")
        nodes[2]["p_geom_m_minus2"] = nodes[1]["p_geom_m_minus2"]
        with self.assertRaises(ValueError):
            project_local_five_nodes(nodes)

    def test_impossible_fixed_boundary_fails_closed(self):
        nodes = source_nodes("MS1")
        nodes[3]["energy_geom_m_minus2"] = nodes[0]["energy_geom_m_minus2"] + 0.001 * (
            nodes[3]["p_geom_m_minus2"] - nodes[0]["p_geom_m_minus2"]
        )
        with self.assertRaises(LocalProjectionNotFeasible):
            project_local_five_nodes(nodes, 0.95)

    def test_positive_source_segment_is_not_changed_unnecessarily(self):
        nodes = source_nodes("MPA1")
        p = [d["p_geom_m_minus2"] for d in nodes]
        e0 = nodes[0]["energy_geom_m_minus2"]
        for i, v in enumerate(nodes):
            v["energy_geom_m_minus2"] = e0 + (p[i] - p[0]) / 0.4
        o = project_local_five_nodes(nodes, cap=0.95)
        self.assertEqual(o["modified_source_indices"], [])
        self.assertEqual(o["source_e_geom"], o["candidate_e_geom"])

if __name__ == "__main__":
    unittest.main()
