import tempfile
import unittest
from pathlib import Path

from precise_apr4_mass_spin_root import (
    MASS_TOL_MSUN, SPIN_TOL_HZ, TARGET_MASS_MSUN, TARGET_SPIN_HZ,
    _norm, parse_output, patch_equilibrium_accuracy, patch_output_precision,
    solve_fixed_mf,
)


class PreciseRNSRootTests(unittest.TestCase):
    def test_diagnostic_patch_changes_one_print_only(self):
        source = '''    printf("%g \\t %4.3f \\t %4.2f \\t %4.1f \\n",
              star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI));\n'''
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rns.c"
            path.write_text(source, encoding="utf-8")
            evidence = patch_output_precision(path)
            patched = path.read_text(encoding="utf-8")
        self.assertEqual(evidence["replacement_count"], 1)
        self.assertEqual(evidence["scope"], "final printf format only; no solver arithmetic changed")
        self.assertIn(r'%.17g\n",', patched)
        self.assertIn("star.Mass_0/MSUN", patched)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "drifted.c"
            path.write_text("printf(\"different\");\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expected one"):
                patch_output_precision(path)

    def test_full_precision_parser_keeps_unrounded_values(self):
        parsed = parse_output("header\n1.757 2.073000123456789 10.7654321098765 "
                              "346.536369012345 2.46987654321098\n", 1.757e15)
        self.assertAlmostEqual(parsed["mass_msun"], 2.073000123456789, places=14)
        self.assertAlmostEqual(parsed["spin_hz"], 346.536369012345, places=12)
        self.assertAlmostEqual(parsed["radius_eq_km"], 10.7654321098765, places=13)
        self.assertAlmostEqual(parsed["rns_M0_using_native_Mb_msun"], 2.46987654321098, places=13)

    def test_equilibrium_accuracy_patch_isolated_and_exact(self):
        source_text = "int rns(void) { double accuracy=1e-4; return 0; }\n"
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "findmodel.c"
            output = Path(d) / "patched" / "findmodel.c"
            source.write_text(source_text, encoding="utf-8")
            before = source.read_bytes()
            expected = before.replace(b"double accuracy=1e-4;", b"double accuracy=1e-9;")
            meta = patch_equilibrium_accuracy(source, output, accuracy=1e-9)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(output.read_bytes(), expected)
        self.assertEqual(meta["replacement_count"], 1)
        self.assertEqual(meta["patched_accuracy"], 1e-9)
        self.assertIn("input source preserved", meta["scope"])

    def test_line_search_merit_uses_preregistered_M_f_tolerances(self):
        self.assertAlmostEqual(_norm((MASS_TOL_MSUN, SPIN_TOL_HZ)), 2**0.5)
        self.assertAlmostEqual(_norm((0.0, SPIN_TOL_HZ)), 1.0)
        self.assertAlmostEqual(_norm((MASS_TOL_MSUN, 0.0)), 1.0)

    def test_2d_newton_solves_both_targets_from_independent_seeds(self):
        def model(ec, ratio):
            u = ec / 1e15
            return {
                "mass_msun": 2.073 + 0.21*(u-1.75) + 0.42*(ratio-.96),
                "spin_hz": TARGET_SPIN_HZ + 120.0*(u-1.75) + 8200.0*(ratio-.96),
                "radius_eq_km": 10.7 + .5*(u-1.75) - .1*(ratio-.96),
                "central_energy_density_g_cm3": ec,
            }
        a = solve_fixed_mf(model, (1.70, .955))
        b = solve_fixed_mf(model, (1.83, .970))
        for result in (a, b):
            self.assertLessEqual(abs(result["mass_msun"]-TARGET_MASS_MSUN), 1e-5)
            self.assertLessEqual(abs(result["spin_hz"]-TARGET_SPIN_HZ), 1e-4)
        self.assertAlmostEqual(a["axis_ratio"], b["axis_ratio"], places=8)
        self.assertLessEqual(abs(a["central_energy_density_g_cm3"]-
                                 b["central_energy_density_g_cm3"]), 1.0e7)
        self.assertTrue(a["root_trace"])

    def test_failed_rns_evaluations_are_retained(self):
        calls = 0
        def failing(ec, ratio):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("simulated failed C solve")
            return {"mass_msun": 2.0, "spin_hz": 300.0}
        with self.assertRaises(RuntimeError) as ctx:
            solve_fixed_mf(failing, (1.75, .96))
        self.assertTrue(ctx.exception.trace)
        self.assertIn("FAILED", [x["status"] for x in ctx.exception.trace])


if __name__ == "__main__":
    unittest.main()

