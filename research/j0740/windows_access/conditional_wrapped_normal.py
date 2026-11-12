"""Normalized conditional wrapped-normal density for a two-phase torus.

The density is represented by its Fourier series. A covariance-eigenvalue bound
controls the omitted lattice tail uniformly on the unit torus; no weight or
density clipping is performed.
"""
from __future__ import annotations

import math
import numpy as np


class ConditionalWrappedNormal2:
    def __init__(self, x_center, phase_location, regression, covariance):
        self.x_center = np.asarray(x_center, dtype=float)
        self.phase_location = np.mod(np.asarray(phase_location, dtype=float), 1.0)
        self.regression = np.asarray(regression, dtype=float)
        self.covariance = np.asarray(covariance, dtype=float)
        d = self.x_center.size
        if self.phase_location.shape != (2,) or self.regression.shape != (2, d):
            raise ValueError("expected phase_location (2,) and regression (2,D)")
        if self.covariance.shape != (2, 2) or not np.allclose(
            self.covariance, self.covariance.T, rtol=0.0, atol=1e-13
        ):
            raise ValueError("covariance must be symmetric 2x2")
        eig = np.linalg.eigvalsh(self.covariance)
        if eig[0] <= 0.0:
            raise ValueError("covariance must be positive definite")
        self.lambda_min = float(eig[0])

    def mean(self, x):
        x = np.asarray(x, dtype=float)
        if x.shape[-1] != self.x_center.size:
            raise ValueError("x has wrong final dimension")
        return np.mod(self.phase_location + (x - self.x_center) @ self.regression.T, 1.0)

    def sample(self, x, rng):
        mean = self.mean(x)
        noise = rng.multivariate_normal(np.zeros(2), self.covariance, size=mean.shape[:-1] or None)
        return np.mod(mean + noise, 1.0)

    def _cutoff(self, tolerance):
        if not (0.0 < tolerance < 1.0):
            raise ValueError("tolerance must be in (0,1)")
        a = 2.0 * math.pi**2 * self.lambda_min
        kmax = 2
        while True:
            first_omitted_shell = kmax + 1
            # For L beyond the maximum of x*exp(-a*x^2), the shell envelope is
            # decreasing and this sum-plus-integral bound is uniform.
            if first_omitted_shell >= 1.0 / math.sqrt(2.0 * a):
                bound = (8.0 * first_omitted_shell + 4.0 / a) * math.exp(
                    -a * first_omitted_shell**2
                )
                if bound <= tolerance:
                    return kmax, bound
            kmax += 1

    def logpdf(self, phase, x, tolerance=1e-12, return_error_bound=False):
        phase = np.asarray(phase, dtype=float)
        if phase.shape[-1] != 2 or np.any(~np.isfinite(phase)):
            raise ValueError("phase must be finite with final dimension 2")
        phase = np.mod(phase, 1.0)
        x = np.asarray(x, dtype=float)
        mean = self.mean(x)
        phase, mean = np.broadcast_arrays(phase, mean)
        kmax, bound = self._cutoff(tolerance)
        axis = np.arange(-kmax, kmax + 1, dtype=float)
        k = np.stack(np.meshgrid(axis, axis, indexing="ij"), axis=-1).reshape(-1, 2)
        quadratic = np.einsum("ki,ij,kj->k", k, self.covariance, k)
        coefficients = np.exp(-2.0 * math.pi**2 * quadratic)
        delta = (phase - mean).reshape(-1, 2)
        values = np.cos(2.0 * math.pi * delta @ k.T) @ coefficients
        values = values.reshape(phase.shape[:-1])
        if np.any(~np.isfinite(values)) or np.any(values <= bound):
            raise ArithmeticError("Fourier density unresolved at requested tolerance")
        answer = np.log(values)
        if return_error_bound:
            return answer, bound
        return answer

