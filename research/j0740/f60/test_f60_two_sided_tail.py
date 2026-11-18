"""F60 source-locked two-sided radio-prior math tests."""
import hashlib
import json
import math
import unittest
from pathlib import Path
from f60_two_sided_tail import (inspect, truncated_normal_cdf, standard_normal_cdf, SOURCE_SHA256)

F51=Path("research/j0740/f51/F51_results.json")

class F60Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=F51.read_bytes()
        cls.r=inspect(cls.raw)

    def test_sha_locked(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(),SOURCE_SHA256)

    def test_normal_cdf_symmetry_and_tails(self):
        self.assertAlmostEqual(standard_normal_cdf(0),.5,places=15)
        for z in [.1,1,2,4]:
            self.assertAlmostEqual(standard_normal_cdf(z)+standard_normal_cdf(-z),1,places=14)

    def test_truncated_mass_density_normalized(self):
        self.assertEqual(truncated_normal_cdf(2.082-5*.0703),0.)
        self.assertEqual(truncated_normal_cdf(2.082+5*.0703),1.)
        self.assertAlmostEqual(truncated_normal_cdf(2.082),.5,places=13)

    def test_original_F51_mass_weight(self):
        w=truncated_normal_cdf(2.10)-truncated_normal_cdf(1.89)
        self.assertAlmostEqual(w,0.597886832314311,places=12)

    def test_low_and_high_mass_split(self):
        r=self.r
        self.assertAlmostEqual(r["mass_prior_below_1p89"],0.0031553809805535,places=12)
        self.assertAlmostEqual(r["mass_prior_above_2p175"],0.0929337767744355,places=12)
        self.assertAlmostEqual(r["total_outside_pair_interval"],0.096089157754989,places=12)
        self.assertAlmostEqual(r["fraction_of_uncomputed_prior_ABOVE_2p175"],0.967161945694,places=11)

    def test_six_existing_kde_pair_integrals(self):
        self.assertEqual(len(self.r["conditional_only_comparisons"]),6)
        for row in self.r["conditional_only_comparisons"]:
            self.assertGreater(row["known_MPA1_minus_ENG_integral_gap"],0.)

    def test_high_tail_reversal_arithmetic(self):
        q=self.r["mass_prior_above_2p175"]
        for row in self.r["conditional_only_comparisons"]:
            self.assertTrue(math.isclose(
                row["unknown_high_tail_mean_ENG_minus_MPA1_needed_if_low_tail_mean_difference_is_zero"]*q,
                row["known_MPA1_minus_ENG_integral_gap"],rel_tol=1e-12))

    def test_support_targets_are_hypothetical(self):
        xs=self.r["hypothetical_upper_mass_extension_targets"]
        cov=[x["mass_prior_coverage_inside_1p89_to_target"] for x in xs]
        self.assertEqual(len(xs),5)
        self.assertTrue(all(cov[i]<cov[i+1] for i in range(4)))
        self.assertTrue(all(0<x["prior_mass_still_outside_window"]<1 for x in xs))
        self.assertAlmostEqual(cov[2],0.988415166107435,places=12)

    def test_reject_wrong_gaussian_parameters(self):
        with self.assertRaisesRegex(ValueError,"INVALID_RADIO_PRIOR"):
            truncated_normal_cdf(2.,sigma=0)

    def test_reject_tampered_F51(self):
        with self.assertRaisesRegex(ValueError,"F51_SHA_DRIFT"):
            inspect(self.raw+b"\n")

    def test_no_unjustified_original_eos_claim(self):
        s=" ".join(self.r["limitations"])
        self.assertIn("not original seven nuclear EOS",s)
        self.assertIn("NOT_ESTABLISHED",s)

if __name__=="__main__": unittest.main()
