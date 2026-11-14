"""Exploratory J0740 13D support-aware importance proposal: MATH ONLY.

The 13D *source-prior normal* latent coordinates remain unchanged.  The two
fitted Gaussian components live in an unconstrained auxiliary ``y`` space and
are pushed to ``z=bound*tanh(y/bound)``.  Density evaluation includes the exact
Jacobian, so no sample/weight clipping or truncated-Gaussian normalization is
required.  An independent, full-support native proposal is kept at weight .75.

This module does not call X-PSI, make an EOS inference, or claim a held-out pass.
The user-supplied native_base must independently establish its own normalized
logpdf(z) and sampling from a 16-dimensional unit coordinate block.
"""
from __future__ import annotations

import hashlib
import json
import math
import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp, ndtri

DIM = 13
LOG2PI = math.log(2 * math.pi)
VERSION = "j0740-support-aware-v3-candidate-1"


class BoundedGaussian:
    """Normalized pushforward of N(mu, cov) by z=B*tanh(y/B)."""

    def __init__(self, mean, cov, bound=7.0):
        self.mean = np.asarray(mean, dtype=np.float64).copy()
        self.cov = np.asarray(cov, dtype=np.float64).copy()
        self.bound = float(bound)
        if not (4 <= self.bound <= 7.0 and np.isfinite(self.bound)):
            raise ValueError("bound must be finite in [4,7] for CDF headroom")
        if self.mean.shape != (DIM,) or self.cov.shape != (DIM, DIM):
            raise ValueError("expected mean (13,) and covariance (13,13)")
        if not (np.isfinite(self.mean).all() and np.isfinite(self.cov).all()):
            raise ValueError("Gaussian parameters must be finite")
        if not np.allclose(self.cov, self.cov.T, rtol=0, atol=1e-12):
            raise ValueError("covariance is not symmetric")
        try:
            self.chol = np.linalg.cholesky(self.cov)
        except np.linalg.LinAlgError as exc:
            raise ValueError("covariance is not positive definite") from exc
        self.lognorm = -.5 * DIM * LOG2PI - np.log(np.diag(self.chol)).sum()

    def from_unit(self, u):
        u = np.asarray(u, dtype=float)
        if u.ndim != 2 or u.shape[1] != DIM or not np.isfinite(u).all():
            raise ValueError("unit draws must have shape (n,13)")
        if np.any((u <= 0) | (u >= 1)):
            raise ValueError("unit endpoints prohibited; never clip")
        y = ndtri(u) @ self.chol.T + self.mean
        z = self.bound * np.tanh(y / self.bound)
        if np.any(np.abs(z) >= self.bound):
            raise ArithmeticError("bounded transform saturated: abort batch, never clip")
        return z

    def logpdf(self, z):
        z = np.asarray(z, dtype=float)
        if z.ndim != 2 or z.shape[1] != DIM or not np.isfinite(z).all():
            raise ValueError("expected finite z with shape (n,13)")
        out = np.full(len(z), -np.inf)
        valid = np.all(np.abs(z) < self.bound, axis=1)
        if np.any(valid):
            zz = z[valid] / self.bound
            y = self.bound * np.arctanh(zz)
            whitened = solve_triangular(self.chol, (y - self.mean).T, lower=True).T
            log_normal = self.lognorm - 0.5 * np.sum(whitened**2, axis=1)
            log_jac = -np.log1p(-zz**2).sum(axis=1)
            out[valid] = log_normal + log_jac
        return out


class DefensiveBoundedMixture:
    """Normalized .75 q_base + .20 q_core + .05 q_broad, all in z coordinates."""
    def __init__(self, native_base, core, broad, fractions=(.75, .20, .05)):
        fractions = np.asarray(fractions, dtype=float)
        if fractions.shape != (3,) or np.any(~np.isfinite(fractions)) or np.any(fractions <= 0) or not np.isclose(fractions.sum(), 1., rtol=0, atol=1e-12):
            raise ValueError("fractions must be three strictly positive probabilities totaling 1")
        if not isinstance(core, BoundedGaussian) or not isinstance(broad, BoundedGaussian):
            raise TypeError("adapted components must be normalized BoundedGaussian")
        if not callable(getattr(native_base, "from_unit", None)) or not callable(getattr(native_base, "logpdf", None)):
            raise ValueError("normalized full-support native base is required")
        self.base = native_base
        self.core, self.broad = core, broad
        self.fractions = fractions.copy()

    def logpdf(self, z):
        z = np.asarray(z, dtype=float)
        if z.ndim != 2 or z.shape[1] != DIM or not np.isfinite(z).all():
            raise ValueError("expected finite z with shape (n,13)")
        a = np.asarray(self.base.logpdf(z), dtype=float)
        if a.shape != (len(z),) or not np.isfinite(a).all():
            raise ValueError("native base must have finite full-support logpdf")
        rows = [math.log(self.fractions[0]) + a,
                math.log(self.fractions[1]) + self.core.logpdf(z),
                math.log(self.fractions[2]) + self.broad.logpdf(z)]
        return logsumexp(np.stack(rows, axis=0), axis=0)

    def from_unit(self, u):
        u = np.asarray(u, dtype=float)
        if u.ndim != 2 or u.shape[1] != 17 or not np.isfinite(u).all():
            raise ValueError("need unit-array (n,17): label + 16 base coordinates")
        if np.any((u <= 0) | (u >= 1)):
            raise ValueError("unit endpoints prohibited; never clip")
        categories = np.searchsorted(np.cumsum(self.fractions), u[:, 0], side="right")
        if np.any(categories > 2):
            raise ArithmeticError("categorical boundary invalid")
        z = np.empty((len(u), DIM))
        for i, component in enumerate((self.base, self.core, self.broad)):
            selected = categories == i
            if np.any(selected):
                draw = component.from_unit(u[selected, 1:17 if i == 0 else 14])
                if draw.shape != (sum(selected), DIM) or not np.isfinite(draw).all():
                    raise ValueError("component returned invalid z")
                z[selected] = draw
        return z


def fit_training_only(z, logw, native_base, *, model_sha256="", broad_scale=1.6,
                      bound=7.0, ridge=0.15, eigen_floor=0.35):
    """Fit *only* preserved training draws, no held-out inputs or likelihood.

    No row is trimmed; -inf log weight is retained with its correct zero
    training weight.  Covariance regularization changes *the proposal*, not
    any recorded importance weight. Must freeze/hash before new hold-out draws.
    """
    z = np.asarray(z, dtype=np.float64)
    logw = np.asarray(logw, dtype=np.float64)
    if z.ndim != 2 or z.shape[1] != DIM or len(z) < 512 or not np.isfinite(z).all():
        raise ValueError("need >=512 finite 13D training draws")
    if logw.shape != (len(z),) or np.isnan(logw).any() or np.isposinf(logw).any() or not np.isfinite(logw).any():
        raise ValueError("invalid training logweights")
    if not (4 <= bound <= 7 and 1 <= broad_scale <= 2.5 and 0 < ridge < 1 and 0 < eigen_floor <= 2):
        raise ValueError("invalid bounded design parameters")
    if np.any(np.abs(z) >= bound):
        raise ValueError("training draw lies outside bounded component; do not discard")
    w = np.exp(logw - logsumexp(logw))
    ess = float(1 / np.dot(w, w))
    if ess < 64:
        raise ValueError("training ESS under frozen minimum 64")
    y = bound * np.arctanh(z / bound)
    mu = w @ y
    centered = y - mu
    cov = (centered * w[:, None]).T @ centered
    cov = (1 - ridge) * cov + ridge * np.eye(DIM)
    eig, eigvec = np.linalg.eigh(cov)
    cov = (eigvec * np.maximum(eig, eigen_floor)) @ eigvec.T
    cov = (cov + cov.T) * .5
    core = BoundedGaussian(mu, cov, bound=bound)
    broad = BoundedGaussian(mu, cov * broad_scale, bound=bound)
    mix = DefensiveBoundedMixture(native_base, core, broad)
    training_hash = hashlib.sha256(z.tobytes() + logw.tobytes()).hexdigest()
    packet = dict(version=VERSION, model_sha256=str(model_sha256),
                  training_sha256=training_hash, rows=len(z),
                  training_ESS=ess, bound=bound, ridge=ridge,
                  eigen_floor=eigen_floor, broad_scale=broad_scale,
                  fractions=mix.fractions.tolist(), mean_y=mu.tolist(),
                  cov_y=cov.tolist())
    identity = hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    info = {"status": "TRAINING_ONLY_CANDIDATE", "heldout_status": "NOT_EVALUATED",
            "EOS_Bayes": "NOT_RUN", "full_MR_convergence": "NOT_ESTABLISHED",
            "training_sha256": training_hash, "proposal_sha256": identity,
            "model_sha256": str(model_sha256), "rows": len(z),
            "training_ESS": ess, "params": packet}
    return mix, info
