"""Fixed-seed public-contract tests, with no NICER data or photon calculations."""
import math
import unittest
import numpy as np
from scipy.special import logsumexp

from defensive_latent_v3 import DefensiveLatentV3, fit_training_only


def latent_logprior(z):
    return -0.5 * (13 * np.log(2.0 * np.pi) + np.sum(z * z, axis=-1))


class DefensiveLatentTests(unittest.TestCase):
    def test_sample_has_finite_density_and_exact_defensive_floor(self):
        model = DefensiveLatentV3(np.zeros(13), np.eye(13))
        points = np.vstack([np.zeros(13), np.full(13, 12.0), np.full(13, -12.0)])
        logq = model.logpdf(points)
        self.assertEqual(logq.shape, (3,))
        self.assertTrue(np.all(np.isfinite(logq)))
        self.assertTrue(np.all(logq >= latent_logprior(points) + math.log(0.5) - 1e-12))
        draw, component = model.sample(8192, np.random.default_rng(101), return_component=True)
        self.assertEqual(draw.shape, (8192, 13))
        self.assertTrue(np.all(np.isfinite(draw)))
        self.assertTrue(np.all(np.isfinite(model.logpdf(draw))))
        self.assertEqual(set(np.unique(component)), {0, 1, 2})

    def test_native_source_cdf_endpoint_stress_guard(self):
        # Must not reproduce the broad-tail endpoint pathology at a fixed seed.
        from scipy.special import ndtr
        model = DefensiveLatentV3(np.zeros(13), np.eye(13))
        latent, labels = model.sample(200000, np.random.default_rng(144), return_component=True)
        u = ndtr(latent)
        boundary_rows = np.any((u <= 0) | (u >= 1), axis=1)
        self.assertEqual(int(boundary_rows.sum()), 0,
                         'proposal generated invalid machine-float source-unit coordinates')

    def test_training_only_fit_is_deterministic_and_preserves_zero_weight_draws(self):
        rng = np.random.default_rng(202)
        z = rng.normal(size=(4096, 13))
        lw = 0.8 * z[:, 0] - 0.4 * z[:, 1]
        lw[13] = -np.inf
        model_a, audit_a = fit_training_only(z, lw)
        model_b, audit_b = fit_training_only(z.copy(), lw.copy())
        self.assertEqual(audit_a['training_sha256'], audit_b['training_sha256'])
        self.assertEqual(audit_a['proposal_sha256'], audit_b['proposal_sha256'])
        self.assertEqual(audit_a['training_draws'], 4096)
        self.assertTrue(audit_a['training_ess'] > 64)
        self.assertFalse(audit_a['heldout_evaluated'])
        self.assertTrue(np.allclose(model_a.logpdf(z[:25]), model_b.logpdf(z[:25]), rtol=0, atol=0))

    def test_independent_synthetic_heldout_improves_ess_without_reweighting_training(self):
        rng = np.random.default_rng(303)
        train = rng.normal(size=(15000, 13))
        # Exact normalized synthetic target N_13(mean,I) with 2D shift.
        mean = np.zeros(13)
        mean[0], mean[1] = 1.2, -0.8
        logw_train = train @ mean - 0.5 * (mean @ mean)
        model, audit = fit_training_only(train, logw_train)
        self.assertTrue(audit['training_ess'] > 64)
        base = rng.normal(size=(20000, 13))
        adapted, _ = model.sample(20000, rng, return_component=True)
        lb = base @ mean - 0.5 * (mean @ mean)
        la = -0.5 * np.sum((adapted - mean)**2, axis=1) - 6.5 * np.log(2.0*np.pi) - model.logpdf(adapted)
        def ess(logw):
            weights = np.exp(logw-logsumexp(logw))
            return 1.0 / np.dot(weights, weights)
        # Only a synthetic property test; not a real J0740 achievement.
        self.assertGreater(ess(la), 1.15*ess(lb))
        self.assertLess(abs((logsumexp(la)-math.log(len(la)))), 0.08)

    def test_density_matches_independent_scipy_oracle(self):
        from scipy.stats import multivariate_normal
        rng = np.random.default_rng(404)
        a = rng.normal(size=(13, 13))
        covariance = a @ a.T / 13 + 0.45 * np.eye(13)
        mean = np.linspace(-0.5, 0.5, 13)
        model = DefensiveLatentV3(mean, covariance)
        probe = rng.normal(size=(24, 13))
        expected = logsumexp(np.stack([
            np.log(0.5) + multivariate_normal.logpdf(probe, mean=np.zeros(13), cov=np.eye(13)),
            np.log(0.4) + multivariate_normal.logpdf(probe, mean=mean, cov=covariance),
            np.log(0.1) + multivariate_normal.logpdf(probe, mean=mean, cov=1.5*covariance),
        ]), axis=0)
        self.assertTrue(np.allclose(model.logpdf(probe), expected, rtol=0, atol=2e-12))

    def test_rejects_invalid_inputs_without_clipping(self):
        with self.assertRaises(ValueError):
            DefensiveLatentV3(np.zeros(13), -np.eye(13))
        with self.assertRaises(ValueError):
            DefensiveLatentV3(np.zeros(13), np.eye(12))
        with self.assertRaises(ValueError):
            DefensiveLatentV3(np.zeros(13), np.eye(13)).logpdf(np.full((3, 13), np.nan))
        with self.assertRaises(ValueError):
            fit_training_only(np.zeros((500, 13)), np.zeros(500))
        with self.assertRaises(ValueError):
            fit_training_only(np.zeros((512, 13)), np.full(512, -np.inf))


if __name__ == '__main__':
    unittest.main()
