"""F52 algorithmic unit tests; mock stars are NOT astrophysical evidence."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import f52_wff1_turnover_scan as f52


class F52Test(unittest.TestCase):
    def fake_star(self, ec, ratio):
        e15 = ec / 1e15
        return {"central_energy_density_g_cm3": ec, "axis_ratio": ratio,
                "spin_hz": f52.SPIN_HZ + 4000 * (.99 - ratio),
                "mass_msun": 2.120 - .02 * (e15 - 3.0) ** 2,
                "radius_eq_km": 9.5 + .1 * (e15 - 3.0),
                "baryonic_M0": "NOT_CALIBRATED"}

    def test_spin_root_is_genuine_evaluator_output(self):
        star, trace = f52.solve_fixed_frequency(self.fake_star, 2.8e15, .988)
        self.assertLess(abs(star["spin_residual_hz"]), f52.SPIN_TOL_HZ)
        self.assertAlmostEqual(star["axis_ratio"], .99, places=7)
        self.assertGreaterEqual(len(trace), 3)
        self.assertEqual(star["mass_msun"], self.fake_star(2.8e15, star["axis_ratio"])["mass_msun"])

    def test_no_spin_bracket_fails_closed(self):
        def no_target(ec, ratio):
            star = self.fake_star(ec, ratio)
            star["spin_hz"] = f52.SPIN_HZ + 200
            return star
        with self.assertRaisesRegex(ValueError, "NO_VALID_DIRECT_C_FIXED_SPIN_BRACKET"):
            f52.solve_fixed_frequency(no_target, 3e15, .99)

    def test_bracketed_peak_is_not_fixed_J_proof(self):
        rows = [self.fake_star(e * 1e15, .99) for e in (2.8, 2.9, 3.0, 3.1, 3.2)]
        result = f52.summarize_turnover(rows)
        self.assertEqual(result["status"], "SAMPLED_FIXED_F_TURNOVER_BRACKETED")
        self.assertAlmostEqual(result["max_sampled_mass_msun"], 2.120)
        self.assertEqual(result["constant_J_stability"], "NOT_TESTED")
        self.assertEqual(result["physical_maximum_mass_certification"], "NOT_ESTABLISHED")
        self.assertIn(2.125, result["old_targets_above_sampled_max"])

    def test_monotonic_curve_not_labeled_turnover(self):
        rows = [self.fake_star(e * 1e15, .99) for e in (2.4, 2.5, 2.6)]
        result = f52.summarize_turnover(rows)
        self.assertEqual(result["status"], "SAMPLED_MAXIMUM_NOT_BRACKETED")

    def test_insufficient_samples_never_certified(self):
        result = f52.summarize_turnover([self.fake_star(3e15, .99)])
        self.assertEqual(result["status"], "INSUFFICIENT_DIRECT_STARS")


if __name__ == "__main__":
    unittest.main()
