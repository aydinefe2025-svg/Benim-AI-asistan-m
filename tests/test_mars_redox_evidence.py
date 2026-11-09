"""Tests for arithmetic and epistemic guardrails on cited Jezero examples."""
import unittest
from research.mars_redox_evidence import (
    QuotedMeasurement, audit_published_numbers, SOURCE_DOI,
)


class MarsRedoxEvidenceTests(unittest.TestCase):
    def test_relative_quoted_uncertainty_matches_division(self):
        report = audit_published_numbers()
        self.assertEqual(SOURCE_DOI, "10.1038/s41586-025-09413-0")
        self.assertEqual([x["element"] for x in report["elements"]], ["Zn", "Ni", "Cu"])
        for record in report["elements"]:
            self.assertAlmostEqual(
                record["relative_quoted_uncertainty_pct"],
                round(100 * record["quoted_uncertainty_ppm"] / record["concentration_ppm"], 2),
            )

    def test_biosignature_and_data_scope_remain_unconfirmed(self):
        p = audit_published_numbers()
        self.assertFalse(p["life_detected"])
        self.assertFalse(p["raw_spectra_reanalysed"])
        self.assertFalse(p["uncertainty_is_biosignature_probability"])

    def test_zero_or_invalid_concentration_rejected(self):
        for pair in ((0, 1), (-10, 1), (10, -1), (float("nan"), 1)):
            with self.subTest(pair=pair), self.assertRaises(ValueError):
                QuotedMeasurement("X", *pair).relative_quoted_uncertainty_pct


if __name__ == "__main__":
    unittest.main()