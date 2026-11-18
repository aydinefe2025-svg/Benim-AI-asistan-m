import math
import unittest
from apr4_lal_rest_mass_baryon_normalization import calculate, M_U_GEOM_M

class LALRestMassNormalizationTests(unittest.TestCase):
    def test_provenance_and_explicit_status(self):
        r = calculate()
        self.assertEqual(r["source_rows"], 865)
        self.assertIn("NOT_INDEPENDENTLY_MEASURED", r["status"])
        self.assertEqual(r["source_npz_sha256"], "639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88")

    def test_surface_mass_unit_is_pinned(self):
        self.assertAlmostEqual(M_U_GEOM_M, 1.2331429241704314e-54, delta=1e-66)

    def test_density_scale_and_monotonicity(self):
        r = calculate()
        first, last = r["n_b_fm-3"]["first_export_sample"], r["n_b_fm-3"]["last_export_sample"]
        self.assertTrue(0 < first < last)
        self.assertAlmostEqual(first, 1.30957588922e-6, delta=1e-15)
        self.assertAlmostEqual(last, 1.80460248264, delta=1e-9)

    def test_jester_proxy_is_not_mistaken_for_first_law_density(self):
        r = calculate()["ratio_to_jester_e_over_mavg_proxy"]
        self.assertAlmostEqual(r["first_export_sample"], 1.0064292384, delta=1e-10)
        self.assertAlmostEqual(r["last_export_sample"], 0.539183875419, delta=1e-10)

if __name__ == "__main__":
    unittest.main()
