"""Normalized defensive mixture on R^11 x T^2, before X-PSI integration.

Mathematical proposal only. No photon likelihood, prior, transport fitting, or
held-out convergence is implemented here. Nonphase latent x is *identity*;
any other transform requires its separately verified Jacobian.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.special import logsumexp, ndtr, ndtri

from conditional_wrapped_normal import ConditionalWrappedNormal2

D = 11
LOG2PI = math.log(2.0 * math.pi)


def _fraction(value, name, allow_zero=True):
    if not np.isscalar(value) or not np.isfinite(value):
        raise ValueError(f"{name} must be a finite scalar")
    v = float(value)
    if v < 0 or v > 1 or (not allow_zero and v == 0):
        raise ValueError(f"{name} must be a probability")
    return v


def _probabilities(weights, count, name):
    w = np.asarray(weights, dtype=float)
    if w.shape != (count,) or np.any(~np.isfinite(w)) or np.any(w < 0):
        raise ValueError(f"{name}: invalid component weights")
    if not np.isclose(w.sum(), 1.0, atol=1e-12, rtol=0):
        raise ValueError(f"{name}: component weights must sum to one")
    return w


def _chol(covariance, dimension, name):
    c = np.asarray(covariance, dtype=float)
    if c.shape != (dimension, dimension) or not np.all(np.isfinite(c)):
        raise ValueError(f"{name}: nonfinite or wrong covariance shape")
    if not np.allclose(c, c.T, rtol=0, atol=1e-12):
        raise ValueError(f"{name}: covariance not symmetric")
    try:
        factor = np.linalg.cholesky(c)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"{name}: covariance must be positive definite") from exc
    return c, factor


class ConditionalGaussianTorus:
    """p(x,phi)=N_D(x;mu,Sigma) WN_2(phi|a+B(x-mu),Omega)."""

    def __init__(self, mean_x, covariance_x, phase_location, regression, covariance_phase):
        self.mean_x = np.asarray(mean_x, dtype=float)
        if self.mean_x.shape != (D,) or not np.all(np.isfinite(self.mean_x)):
            raise ValueError("expected finite nonphase mean of length 11")
        self.covariance_x, self.chol = _chol(covariance_x, D, "nonphase")
        self.phase = ConditionalWrappedNormal2(
            self.mean_x, phase_location, regression, covariance_phase
        )
        if not np.all(np.isfinite(self.phase.phase_location)) or not np.all(
            np.isfinite(self.phase.regression)
        ):
            raise ValueError("nonfinite phase parameters")
        if not np.all(np.isfinite(self.phase.covariance)):
            raise ValueError("nonfinite phase covariance")
        self.log_norm = -0.5 * D * LOG2PI - np.log(np.diag(self.chol)).sum()

    def logpdf(self, x, phase):
        x = np.asarray(x, dtype=float)
        if x.shape[-1] != D or np.any(~np.isfinite(x)):
            raise ValueError("invalid nonphase latent coordinates")
        residual = x - self.mean_x
        whitened = np.linalg.solve(self.chol, residual.reshape(-1, D).T).T
        lognormal = self.log_norm - 0.5 * np.sum(whitened**2, axis=1)
        lognormal = lognormal.reshape(residual.shape[:-1])
        return lognormal + self.phase.logpdf(phase, x)

    def sample(self, n, rng):
        if not isinstance(n, int) or n < 1:
            raise ValueError("positive integer sample count required")
        x = rng.multivariate_normal(self.mean_x, self.covariance_x, size=n)
        return x, self.phase.sample(x, rng)


class DefensiveGaussianTorus:
    """Convex mixture with standard-normal x/uniform phase defensive base.

    Each core and broad component is individually normalized on R^11 x T^2.
    Mixture weights are exact; no clipping, sample filtering or rescaling.
    """

    def __init__(self, core, broad, core_weights, broad_weights,
                 base_fraction=0.50, core_fraction=0.25, broad_fraction=0.25):
        self.core = tuple(core)
        self.broad = tuple(broad)
        if not self.core or not self.broad or any(
            not isinstance(v, ConditionalGaussianTorus)
            for v in (*self.core, *self.broad)
        ):
            raise ValueError("core/broad must contain normalized conditional components")
        self.core_weights = _probabilities(core_weights, len(self.core), "core")
        self.broad_weights = _probabilities(broad_weights, len(self.broad), "broad")
        self.fractions = np.array([
            _fraction(base_fraction, "base"),
            _fraction(core_fraction, "core"),
            _fraction(broad_fraction, "broad"),
        ])
        if not np.isclose(self.fractions.sum(), 1.0, atol=1e-12, rtol=0):
            raise ValueError("defensive fractions must sum to one")

    @staticmethod
    def _coordinates(x, phase):
        x = np.asarray(x, dtype=float)
        phase = np.asarray(phase, dtype=float)
        if x.ndim == 0 or x.shape[-1] != D:
            raise ValueError("nonphase coordinate must have length 11")
        if phase.ndim == 0 or phase.shape[-1] != 2:
            raise ValueError("phase coordinate must have length 2")
        if not np.all(np.isfinite(x)) or not np.all(np.isfinite(phase)):
            raise ValueError("coordinates must be finite")
        shape = np.broadcast_shapes(x.shape[:-1], phase.shape[:-1])
        return np.broadcast_to(x, shape + (D,)), np.broadcast_to(phase, shape + (2,))

    def logpdf(self, x, phase):
        x, phase = self._coordinates(x, phase)
        base = -0.5 * np.sum(x**2, axis=-1) - 0.5 * D * LOG2PI
        terms = []
        if self.fractions[0]:
            terms.append(base + math.log(self.fractions[0]))
        for fraction, comps, weights in (
            (self.fractions[1], self.core, self.core_weights),
            (self.fractions[2], self.broad, self.broad_weights),
        ):
            if fraction:
                terms.extend(
                    comp.logpdf(x, phase) + math.log(fraction * float(weight))
                    for comp, weight in zip(comps, weights) if weight > 0
                )
        return logsumexp(np.stack(terms, axis=0), axis=0)

    def sample(self, n, rng):
        if not isinstance(n, int) or n < 1:
            raise ValueError("positive integer sample count required")
        labels = rng.choice(3, size=n, p=self.fractions)
        x = np.empty((n, D), dtype=float)
        phase = np.empty((n, 2), dtype=float)
        mask = labels == 0
        if mask.any():
            x[mask] = rng.normal(size=(int(mask.sum()), D))
            phase[mask] = rng.uniform(size=(int(mask.sum()), 2))
        for category, comps, weights in (
            (1, self.core, self.core_weights), (2, self.broad, self.broad_weights)
        ):
            indices = np.flatnonzero(labels == category)
            if not len(indices):
                continue
            chosen = rng.choice(len(comps), size=len(indices), p=weights)
            for k, comp in enumerate(comps):
                targets = indices[chosen == k]
                if len(targets):
                    x[targets], phase[targets] = comp.sample(len(targets), rng)
        return x, phase

    @staticmethod
    def _phase_indices(phase_indices):
        if len(phase_indices) != 2 or any(type(i) is not int for i in phase_indices):
            raise ValueError("phase_indices must be two distinct integer positions")
        primary, secondary = phase_indices
        if primary == secondary or any(i < 0 or i >= D + 2 for i in phase_indices):
            raise ValueError("invalid phase indices")
        return primary, secondary

    def logpdf_latent_z(self, z, *, phase_indices):
        """Density for z~R^13 when x is the other 11 identity coordinates.

        phi=(Phi(z_secondary), (Phi(z_primary)-Phi(z_secondary)) mod 1).
        The Jacobian |d(phi)/d(z_primary,z_secondary)| is
        standard_normal_pdf(z_primary)*standard_normal_pdf(z_secondary).
        A non-identity x transform requires a separate Jacobian and must NOT
        use this interface without adjustment.
        """
        primary, secondary = self._phase_indices(phase_indices)
        z = np.asarray(z, dtype=float)
        if z.ndim == 0 or z.shape[-1] != D + 2 or not np.all(np.isfinite(z)):
            raise ValueError("expected finite 13-dimensional z")
        up, us = ndtr(z[..., primary]), ndtr(z[..., secondary])
        if np.any((up <= 0) | (up >= 1) | (us <= 0) | (us >= 1)):
            raise ArithmeticError("Gaussian CDF endpoint: latent Jacobian unresolved")
        phi = np.stack([us, np.mod(up - us, 1.0)], axis=-1)
        x = np.delete(z, (primary, secondary), axis=-1)
        jac = -0.5 * (z[..., primary]**2 + z[..., secondary]**2) - LOG2PI
        return self.logpdf(x, phi) + jac

    def sample_latent_z(self, n, rng, *, phase_indices):
        primary, secondary = self._phase_indices(phase_indices)
        x, phi = self.sample(n, rng)
        up = np.mod(phi[:, 0] + phi[:, 1], 1.0)
        us = phi[:, 0]
        if np.any((up <= 0) | (up >= 1) | (us <= 0) | (us >= 1)):
            raise ArithmeticError("Gaussian inverse-CDF boundary: do not clip samples")
        z = np.empty((n, D + 2), dtype=float)
        indices = [i for i in range(D + 2) if i not in (primary, secondary)]
        z[:, indices] = x
        z[:, primary], z[:, secondary] = ndtri(up), ndtri(us)
        return z
