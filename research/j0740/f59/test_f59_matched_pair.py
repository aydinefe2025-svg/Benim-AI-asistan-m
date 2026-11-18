"""F59 fail-closed locked original F51 science checks."""
import hashlib
import json
import math
import unittest
from pathlib import Path
from f59_matched_pair_extended_support import analyze, PINNED_F51_SHA256

SOURCE = Path("research/j0740/f51/F51_results.json")

class F59Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = SOURCE.read_bytes()
        cls.result = analyze(cls.raw)

    def test_original_f51_sha(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), PINNED_F51_SHA256)

    def test_six_reconstructed_kde(self):
        self.assertEqual(len(self.result["six_surface_details"]),6)

    def test_known_prior_mass_partition_sums_to_unity(self):
        b = self.result["prior_mass_fractions"]
        self.assertAlmostEqual(sum(b.values()),1,places=12)
        self.assertAlmostEqual(b["outside_1p89_to_2p175"],0.09608915775498905,places=12)

    def test_reproduce_short_window_pattern(self):
        rows=self.result["six_surface_details"]
        self.assertEqual([r["leader_in_1p89_to_2p10"] for r in rows].count("ENG"),2)
        self.assertEqual([r["leader_in_1p89_to_2p10"] for r in rows].count("MPA1"),4)

    def test_reproduce_extended_pairwise_leaders(self):
        self.assertEqual(self.result["pairwise_extended_winner_count"],{"MPA1":6,"ENG":0})

    def test_exact_arithmetic_threshold_formula(self):
        q=self.result["prior_mass_fractions"]["outside_1p89_to_2p175"]
        for row in self.result["six_surface_details"]:
            self.assertGreater(row["MPA1_minus_ENG_extended_integral"],0)
            self.assertTrue(math.isclose(
                row["minimum_missing_tail_mean_ENG_minus_MPA1_to_reverse"]*q,
                row["MPA1_minus_ENG_extended_integral"], rel_tol=1e-12))

    def test_support_not_claimed_for_all_seven(self):
        self.assertTrue(any("WFF1" in s for s in self.result["nonclaims"]))
        self.assertTrue(any("APR4_EPP" in s for s in self.result["nonclaims"]))

    def test_tampered_source_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"UNPINNED"):
            analyze(self.raw + b"\n")

    def test_deterministic_output_from_original_source(self):
        self.assertEqual(
            json.dumps(analyze(self.raw),sort_keys=True),
            json.dumps(analyze(self.raw),sort_keys=True))

if __name__=="__main__": unittest.main()
