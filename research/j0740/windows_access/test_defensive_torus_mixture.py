"""Independent math checks for normalized 11D + 2D defensive proposal."""
import math
import unittest
import numpy as np
from scipy.special import ndtr
from scipy.stats import multivariate_normal

from defensive_torus_mixture import (
    ConditionalGaussianTorus, DefensiveGaussianTorus, D, LOG2PI
)


def make():
    mu = np.zeros(D)
    mu[0] = 0.2
    b = np.zeros((2, D))
    b[0, 0], b[1, 0] = 0.25, -0.12
    core = ConditionalGaussianTorus(mu, np.eye(D) * 0.8,
                                    [0.91, 0.07], b,
                                    [[0.035, 0.012], [0.012, 0.046]])
    broad = ConditionalGaussianTorus(mu, np.eye(D) * 3.2,
                                     [0.91, 0.07], b,
                                     [[0.12, 0.01], [0.01, 0.14]])
    return DefensiveGaussianTorus([core], [broad], [1.0], [1.0]), core, broad


class DefensiveTorusTests(unittest.TestCase):
    def test_torus_grid_integrates_to_correct_x_marginal(self):
        q, core, broad = make()
        grid_axis = (np.arange(48) + 0.5) / 48
        grid = np.stack(np.meshgrid(grid_axis, grid_axis, indexing="ij"), axis=-1)
        for value in (0.0, 1.1):
            x = np.zeros(D)
            x[0] = value
            observed = float(np.exp(q.logpdf(x, grid)).mean())
            expected = (0.5 * multivariate_normal.pdf(x, np.zeros(D), np.eye(D))
                        + 0.25 * multivariate_normal.pdf(x, core.mean_x, core.covariance_x)
                        + 0.25 * multivariate_normal.pdf(x, broad.mean_x, broad.covariance_x))
            self.assertAlmostEqual(observed, expected, delta=expected * 1e-9)

    def test_logpdf_matches_independent_three_component_formula(self):
        q, core, broad = make()
        x = np.zeros(D)
        x[0] = -0.24
        phi = np.array([0.12, 0.88])
        expected = np.log(0.5 * multivariate_normal.pdf(x, np.zeros(D), np.eye(D))
            + 0.25 * np.exp(core.logpdf(x, phi))
            + 0.25 * np.exp(broad.logpdf(x, phi)))
        self.assertAlmostEqual(float(q.logpdf(x, phi)), float(expected), places=11)

    def test_latent_z_transform_includes_both_phase_jacobians(self):
        q, _, _ = make()
        z = np.random.default_rng(88).normal(size=(7, D + 2))
        a, b = 2, 9
        up, us = ndtr(z[:, a]), ndtr(z[:, b])
        phi = np.stack([us, np.mod(up-us, 1.0)], axis=-1)
        x = np.delete(z, (a, b), axis=1)
        manual = q.logpdf(x, phi) - 0.5*(z[:, a]**2+z[:, b]**2) - LOG2PI
        np.testing.assert_allclose(q.logpdf_latent_z(z, phase_indices=(a,b)), manual, rtol=0, atol=2e-13)

    def test_sampler_z_inverse_map_and_finite_density(self):
        q, _, _ = make()
        a = q.sample_latent_z(1200, np.random.default_rng(12345), phase_indices=(1,8))
        b = q.sample_latent_z(1200, np.random.default_rng(12345), phase_indices=(1,8))
        np.testing.assert_array_equal(a, b)
        self.assertTrue(np.isfinite(q.logpdf_latent_z(a[:70], phase_indices=(1,8))).all())
        self.assertEqual(a.shape, (1200,13))

    def test_base_only_is_13_dimensional_standard_normal(self):
        q, _, _ = make()
        pure = DefensiveGaussianTorus(q.core, q.broad, [1.0], [1.0],
                                      base_fraction=1.0, core_fraction=0.0, broad_fraction=0.0)
        z = np.random.default_rng(987).normal(size=(9,13))
        expected = -0.5*(z*z).sum(axis=-1) - 0.5*13*LOG2PI
        np.testing.assert_allclose(pure.logpdf_latent_z(z, phase_indices=(0,12)), expected, rtol=0, atol=2e-13)

    def test_invalid_component_and_unnormalized_weights_fail_closed(self):
        q, c, b = make()
        with self.assertRaises(ValueError):
            DefensiveGaussianTorus([c], [b], [0.9], [1.0])
        with self.assertRaises(ValueError):
            DefensiveGaussianTorus([c], [b], [1.0], [1.0], base_fraction=.6)
        with self.assertRaises(ValueError):
            ConditionalGaussianTorus(np.zeros(D), np.eye(D)*-1,
                                     [0.2,0.3], np.zeros((2,D)), np.eye(2)*.05)
        with self.assertRaises(ValueError):
            q.logpdf_latent_z(np.zeros(13), phase_indices=(2,2))
        with self.assertRaises(ArithmeticError):
            q.logpdf_latent_z(np.array([100.0]+[0.0]*12), phase_indices=(0,3))


if __name__ == "__main__":
    unittest.main()
