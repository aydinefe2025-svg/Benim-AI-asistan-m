"""Regression checks for source-pinned 2026 five-joule SOC exact inference."""
import importlib.util
from pathlib import Path
import sys
import unittest

MODULE_DIR = Path(__file__).resolve().parents[1] / "research" / "battery_curve_audit"
sys.path.insert(0, str(MODULE_DIR))
from impact_2026_exact_soc_survival import (
    audit, fisher_two_sided, fisher_three_by_two_equal_groups, holm_adjust
)


class PublishedExactSocTest(unittest.TestCase):
    def setUp(self):
        self.data = audit()

    def test_source_is_45_independent_cells_not_cycles(self):
        self.assertEqual(self.data["cohort"]["total_physically_impacted_cells"], 45)
        self.assertEqual(self.data["cohort"]["survived_after_one_week_by_energy"], {"3J":15,"5J":9,"7J":0})

    def test_five_j_soc_source_counts(self):
        d = {row["soc_percent"]: row["survived_one_week"] for row in self.data["five_j_soc_subgroups"]}
        self.assertEqual(d, {0:1, 20:5, 40:3})
        self.assertEqual(sum(d.values()),9)

    def test_global_3x2_probability_ordering_exact(self):
        self.assertAlmostEqual(fisher_three_by_two_equal_groups((1,5,3),5), 0.06593406593406594, places=14)
        self.assertGreater(self.data["five_j_global_exact_fixed_margin_p"], 0.05)

    def test_global_fisher_invariant_to_soc_group_permutation(self):
        self.assertAlmostEqual(fisher_three_by_two_equal_groups((3,1,5),5), 0.06593406593406594, places=14)

    def test_exact_two_sided_and_zero_cell_cases(self):
        self.assertAlmostEqual(fisher_two_sided(1,5,5,5), 0.047619047619047616)
        self.assertAlmostEqual(fisher_two_sided(15,15,0,15), 1.28934500757877e-08, places=14)

    def test_holm_correction_prevents_false_soc_claim(self):
        a = self.data["five_j_pairwise_fisher_two_sided_raw_p"]
        h = self.data["five_j_pairwise_holm_familywise_p"]
        self.assertEqual(set(a), set(h))
        self.assertAlmostEqual(a["0_vs_20_soc_percent"], 1/21)
        self.assertAlmostEqual(h["0_vs_20_soc_percent"], 1/7)
        self.assertTrue(all(p>=0.05 for p in h.values()))

    def test_energy_group_difference_but_not_capacity_model(self):
        p = self.data["energy_pairwise_holm_familywise_p"]
        self.assertTrue(all(value < 0.05 for value in p.values()))
        self.assertFalse(self.data["statistical_limits"]["seven_j_survivor_capacity_trajectory_identifiable"])
        self.assertTrue(self.data["statistical_limits"]["do_not_replace_failed_cells_capacity_with_zero"])

    def test_nonzero_sensitivity_and_invalid_inputs(self):
        self.assertEqual(fisher_two_sided(0,5,0,5), 1.0)
        with self.assertRaises(ValueError):
            fisher_two_sided(6,5,0,5)
        with self.assertRaises(ValueError):
            fisher_three_by_two_equal_groups((1,2),5)
        with self.assertRaises(ValueError):
            holm_adjust({"bad":1.5})


if __name__=="__main__":
    unittest.main()
