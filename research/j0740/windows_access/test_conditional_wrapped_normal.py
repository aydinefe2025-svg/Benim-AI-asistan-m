import unittest
import numpy as np

from conditional_wrapped_normal import ConditionalWrappedNormal2


class ConditionalWrappedNormalTests(unittest.TestCase):
    def make_model(self, covariance=None):
        if covariance is None:
            covariance = np.array([[0.035, 0.011], [0.011, 0.052]])
        return ConditionalWrappedNormal2(
            x_center=np.array([0.2, -0.3]),
            phase_location=np.array([0.91, 0.08]),
            regression=np.array([[0.13, -0.07], [0.09, 0.16]]),
            covariance=np.asarray(covariance),
        )

    def test_grid_integral_is_one_for_multiple_conditional_means(self):
        model = self.make_model()
        axis = (np.arange(128) + 0.5) / 128
        grid = np.stack(np.meshgrid(axis, axis, indexing="ij"), axis=-1)
        for x in (np.array([0.2, -0.3]), np.array([1.1, -1.4])):
            density = np.exp(model.logpdf(grid, x, tolerance=1e-12))
            self.assertAlmostEqual(float(density.mean()), 1.0, delta=2e-8)

    def test_fourier_density_matches_independent_wrapped_gaussian_sum(self):
        covariance = np.array([[0.018, 0.004], [0.004, 0.026]])
        model = self.make_model(covariance)
        rng = np.random.default_rng(7812)
        phase = rng.uniform(0.0, 1.0, size=(32, 2))
        x = np.array([0.61, -0.77])
        mean = model.mean(x)
        inv = np.linalg.inv(covariance)
        norm = 1.0 / (2.0 * np.pi * np.sqrt(np.linalg.det(covariance)))
        shifts = np.stack(np.meshgrid(np.arange(-5, 6), np.arange(-5, 6), indexing="ij"), axis=-1).reshape(-1, 2)
        delta = phase[:, None, :] + shifts[None, :, :] - mean
        direct = norm * np.exp(-0.5 * np.einsum("nki,ij,nkj->nk", delta, inv, delta)).sum(axis=1)
        actual = np.exp(model.logpdf(phase, x, tolerance=1e-13))
        np.testing.assert_allclose(actual, direct, rtol=2e-11, atol=2e-12)

    def test_samples_match_conditional_wrapped_fourier_moments(self):
        model = self.make_model()
        x = np.array([0.72, -0.91])
        n = 80000
        rng = np.random.default_rng(93017)
        draws = model.sample(np.broadcast_to(x, (n, 2)), rng)
        mean = model.mean(x)
        for frequency in (np.array([1, 0]), np.array([0, 1]), np.array([1, 1])):
            empirical = np.exp(2j * np.pi * draws @ frequency).mean()
            expected = np.exp(2j * np.pi * mean @ frequency - 2 * np.pi**2 * frequency @ model.covariance @ frequency)
            self.assertLess(abs(empirical - expected), 0.012)

    def test_rejects_non_positive_definite_covariance(self):
        with self.assertRaises(ValueError):
            self.make_model(np.array([[0.01, 0.02], [0.02, 0.01]]))


if __name__ == "__main__":
    unittest.main()

