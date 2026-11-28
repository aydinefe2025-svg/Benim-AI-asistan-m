"""Fail-closed standardized-prior latent bridge; NOT a native X-PSI likelihood.

For z~N(0,I_13), original source-unit inputs are u=Phi(z). When the
source-run-verified inverse/conditional prior transform consumes u, the
importance numerator in z is logL(source_transform(u)) + log(phi_13(z)).
The conditional prior's *physical-coordinate* Jacobian must NOT be applied
again: that would double-count the change of variables.

No source prior, photon likelihood, or native EOS inference is included here.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.special import ndtr, ndtri, logsumexp

N_DIMENSIONS = 13
LOG2PI = math.log(2 * math.pi)


def _valid_array(values, name):
    a = np.asarray(values, dtype=float)
    if a.ndim == 0 or a.shape[-1] != N_DIMENSIONS or not np.all(np.isfinite(a)):
        raise ValueError(f"{name} must be a finite array with last dimension 13")
    return a


def latent_to_source_unit(z):
    """Convert z -> original source-prior u, NOT common/relative torus phases."""
    z = _valid_array(z, "z")
    u = ndtr(z)
    if np.any((u <= 0.0) | (u >= 1.0)):
        raise ArithmeticError("Gaussian CDF hit an endpoint; no clipping is allowed")
    return u


def source_unit_to_latent(u):
    """Inverse standardized prior mapping; reject unit-cube endpoints."""
    u = _valid_array(u, "u")
    if np.any((u <= 0.0) | (u >= 1.0)):
        raise ValueError("source unit coordinates must be strictly inside (0, 1)")
    z = ndtri(u)
    if not np.all(np.isfinite(z)):
        raise ArithmeticError("invalid inverse Gaussian CDF result")
    return z


def audit_importance_batch(proposal, z, log_likelihood_from_source_unit,
                           *, phase_indices):
    """Audit all supplied draws with a source-unit callback and proposal q_Z.

    The callback must separately be verified to use the original source-run
    conditional prior transport, boundaries and photon log likelihood.
    -inf logL means physical rejection and contributes exactly zero weight;
    samples are NEVER dropped or clipped. This function alone does not
    establish any real-data inference, normalization or EOS convergence.
    """
    z = _valid_array(z, "z")
    if z.ndim != 2 or z.shape[0] == 0:
        raise ValueError("z must contain one or more 13D rows")
    if (len(phase_indices) != 2 or len(set(phase_indices)) != 2 or
        any(type(k) is not int or not 0 <= k < N_DIMENSIONS for k in phase_indices)):
        raise ValueError("two distinct integer phase indices are required")
    u = latent_to_source_unit(z)
    logL = np.asarray(log_likelihood_from_source_unit(u), dtype=float)
    if logL.shape != (len(z),) or np.any(np.isnan(logL)) or np.any(np.isposinf(logL)):
        raise ValueError("source-unit callback must return length-n logL, finite or -inf")
    logq = np.asarray(proposal.logpdf_latent_z(z, phase_indices=phase_indices), dtype=float)
    if logq.shape != (len(z),) or not np.all(np.isfinite(logq)):
        raise ValueError("proposal log q_Z must be finite for all supplied draws")
    log_prior_z = -0.5 * np.sum(z*z, axis=1) - 0.5 * N_DIMENSIONS * LOG2PI
    logw = logL + log_prior_z - logq
    finite = np.isfinite(logw)
    if not finite.any():
        raise ValueError("no likelihood-supported sample: evidence unresolved")
    logZ = logsumexp(logw) - math.log(len(z))
    weights = np.exp(logw - logsumexp(logw))
    return {
        "status": "SYNTHETIC_OR_USER_CALLBACK_ONLY",
        "raw_draws": int(len(z)),
        "finite_likelihood_draws": int(finite.sum()),
        "ESS": float(1.0 / np.dot(weights, weights)),
        "max_weight_fraction": float(weights.max()),
        "log_evidence": float(logZ),
        "samples_deleted_or_weights_clipped": False,
        "source_prior_transport_identity": "NOT_VERIFIED_BY_THIS_MODULE",
        "EOS_Bayes": "NOT_RUN",
    }
