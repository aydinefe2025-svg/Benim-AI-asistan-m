"""Synthetic/analytical tests only; not native X-PSI data or a source prior proof."""
import math
import unittest
import numpy as np
from scipy.special import logsumexp
from support_normalization_gate import conditional_evidence, wilson_support_interval


class SupportNormalizationGateTests(unittest.TestCase):
    def test_analytic_quarter_support_corrects_raw_integral(self):
        result = conditional_evidence(math.log(.25),
            measure='unconditioned_support_indicator', support_probability=.25,
            provenance='synthetic_exact')
        self.assertAlmostEqual(result['conditional_log_evidence'], 0., places=13)
        self.assertAlmostEqual(result['raw_log_integral'], math.log(.25), places=13)
        self.assertEqual(result['status'], 'MATHEMATICAL_ONLY_SOURCE_NOT_VERIFIED')

    def test_existing_conditional_measure_no_double_correction(self):
        result = conditional_evidence(-3.5, measure='already_conditional')
        self.assertEqual(result['conditional_log_evidence'], -3.5)
        with self.assertRaises(ValueError):
            conditional_evidence(-3.5, measure='already_conditional',
                                 support_probability=.24947354926879406)

    def test_unknown_measure_fails_closed(self):
        with self.assertRaises(ValueError): conditional_evidence(0., measure='unknown')
        with self.assertRaises(ValueError): conditional_evidence(0., measure='unconditioned_support_indicator')
        with self.assertRaises(ValueError): conditional_evidence(0., measure='unconditioned_support_indicator',support_probability=.25,provenance='')

    def test_invalid_support_mass_rejected(self):
        for val in (0., -1., 1.01, float('nan'), float('inf'), True):
            with self.subTest(val=val), self.assertRaises(ValueError):
                conditional_evidence(0., measure='unconditioned_support_indicator', support_probability=val,provenance='toy')
        with self.assertRaises(ValueError): conditional_evidence(float('inf'),measure='already_conditional')

    def test_exact_half_space_quarter_discrete_integration(self):
        # Deterministic equal-mass unit-prior grid: support is u0<1/4.
        n=4096
        u0=(np.arange(n)+0.5)/n
        logL=np.where(u0 < .25, 0., -np.inf)
        raw=logsumexp(logL)-math.log(n)
        self.assertAlmostEqual(raw, math.log(.25), places=14)
        result=conditional_evidence(raw, measure='unconditioned_support_indicator',
                                  support_probability=.25, provenance='synthetic_exact_grid')
        self.assertAlmostEqual(result['conditional_log_evidence'],0.,places=14)

    def test_support_uncertainty_is_not_hidden(self):
        lo,hi=wilson_support_interval(25,100)
        self.assertLess(lo, .25);self.assertGreater(hi,.25)
        result=conditional_evidence(math.log(.25),measure='unconditioned_support_indicator',
                                   support_probability=.25, provenance='synthetic_binomial',support_counts=(25,100))
        self.assertLess(result['conditional_log_evidence_bounds_95'][0],0.)
        self.assertGreater(result['conditional_log_evidence_bounds_95'][1],0.)
        self.assertEqual(result['support_interval_type'],'WILSON_95_BINOMIAL_ONLY')

    def test_zero_success_cannot_claim_finite_corrected_evidence(self):
        with self.assertRaises(ValueError): wilson_support_interval(0,100)
        with self.assertRaises(ValueError): conditional_evidence(0.,measure='unconditioned_support_indicator',
                                                               support_probability=.1, provenance='x',support_counts=(0,100))

    def test_metadata_cannot_be_misread_as_native_eos(self):
        a=conditional_evidence(-1.e5,measure='unconditioned_support_indicator',
                               support_probability=.24947354926879406,provenance='recorded_value_unverified_for_this_run')
        self.assertTrue(np.isfinite(a['conditional_log_evidence']))
        self.assertEqual(a['EOS_Bayes'], 'NOT_RUN')
        self.assertEqual(a['source_prior_lineage_verified'], False)


if __name__ == '__main__': unittest.main()
