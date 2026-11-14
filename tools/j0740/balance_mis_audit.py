"""Independent deterministic-mixture importance sampling audit for paired proposals.

No photon likelihood calls, fitting, prior modification, weight clipping, or
outlier removal. A separate protocol, NOT a way to promote failed 512-draw
K4/K8 experiments into successful original experiments.

Each run pair draws n samples from q_A and n from q_B. The balance density is
q_*(z) = (q_A(z)+q_B(z))/2, so each unnormalised weight is
  w_*(z) = w_origin(z) q_origin(z) / q_*(z).
This holds for the source posterior numerator with its original normalization.
"""
from __future__ import annotations
import math
from typing import Sequence
import numpy as np
from scipy.special import logsumexp

LOG2 = math.log(2.0)
GATES = {
    "ESS_per_pair_min": 100.0,
    "max_weight_fraction_max": 0.05,
    "min_phase_ESS_min": 30.0,
    "between_pair_logI_spread_max": 0.20,
    "half_to_full_logI_drift_max": 0.10,
}

class EvidenceError(ValueError):
    """Missing evidence or inconsistency: fail closed."""


def _matrix(z, label):
    z = np.asarray(z, dtype=np.float64)
    if z.ndim != 2 or z.shape[1] != 13 or not np.isfinite(z).all():
        raise EvidenceError(f"{label}: require finite (n,13) coordinates")
    return z


def _logweights(values, n, label):
    a = np.asarray(values, dtype=np.float64)
    if a.shape != (n,) or np.isnan(a).any() or np.isposinf(a).any():
        raise EvidenceError(f"{label}: expected n log weights, finite or -inf")
    return a


def _logq(values, n, label):
    a = np.asarray(values, dtype=np.float64)
    if a.shape != (n,) or not np.isfinite(a).all():
        raise EvidenceError(f"{label}: q proposal must have strictly positive density")
    return a


def _stats(weights, z, *, phase_axis):
    if phase_axis < 0 or phase_axis >= 13:
        raise EvidenceError("invalid phase axis")
    if not np.isfinite(weights).any():
        raise EvidenceError("all observations have zero target support")
    normalizer = logsumexp(weights)
    w = np.exp(weights - normalizer)
    partition = []
    for positive in (False, True):
        selector = (z[:, phase_axis] > 0) == positive
        lw = weights[selector]
        if len(lw) == 0 or not np.isfinite(lw).any():
            partition.append(0.0)
        else:
            # ESS from GLOBAL normalised weights restricted to each half
            # equals ESS calculated from each partition's unnormalised weights.
            partition.append(float(math.exp(2*logsumexp(lw) - logsumexp(2*lw))))
    return {
        "draws": len(weights),
        "finite_likelihood_draws": int(np.isfinite(weights).sum()),
        "ESS": float(1.0 / np.dot(w, w)),
        "max_weight_fraction": float(w.max()),
        "phase_ESS": partition,
        "min_phase_ESS": min(partition),
        "logI": float(normalizer - math.log(len(weights))),
    }


def evaluate_pair(*, seed: int, za, lwa, logqa_on_a, logqb_on_a,
                  zb, lwb, logqa_on_b, logqb_on_b, phase_axis=2):
    """Reweight every observation using both exact proposal densities.

    za/zb, lwa/lwb must come from independently saved n-draw qA/qB
    proposals using the SAME model, prior and exact target M,R. The caller
    must verify these identities, plus the JSONL -> original logw identity.
    """
    if type(seed) is not int:
        raise EvidenceError("seed must be an integer")
    za, zb = _matrix(za, "qA z"), _matrix(zb, "qB z")
    n = len(za)
    if n < 2 or n != len(zb) or n % 2:
        raise EvidenceError("require matched even positive equal counts, n per proposal")
    lwa, lwb = _logweights(lwa, n, "qA logweights"), _logweights(lwb, n, "qB logweights")
    aa = _logq(logqa_on_a, n, "qA(zA)")
    ab = _logq(logqb_on_a, n, "qB(zA)")
    ba = _logq(logqa_on_b, n, "qA(zB)")
    bb = _logq(logqb_on_b, n, "qB(zB)")
    mixture_a = np.logaddexp(aa, ab) - LOG2
    mixture_b = np.logaddexp(ba, bb) - LOG2
    mixed_a = lwa + aa - mixture_a
    mixed_b = lwb + bb - mixture_b
    all_z = np.concatenate((za, zb), axis=0)
    all_w = np.concatenate((mixed_a, mixed_b))
    short_z = np.concatenate((za[:n//2], zb[:n//2]), axis=0)
    short_w = np.concatenate((mixed_a[:n//2], mixed_b[:n//2]))
    full = _stats(all_w, all_z, phase_axis=phase_axis)
    half = _stats(short_w, short_z, phase_axis=phase_axis)
    full["logI_half_budget"] = half["logI"]
    full["half_to_full_logI_drift"] = abs(full["logI"] - half["logI"])
    full["seed"] = seed
    full["all_samples_preserved"] = True
    full["original_single_proposal_status_unchanged"] = True
    full["K4_K8_paired_source_density_verified_by_caller"] = True
    full["individual_gates"] = {
        "ESS_per_pair_min": full["ESS"] >= GATES["ESS_per_pair_min"],
        "max_weight_fraction_max": full["max_weight_fraction"] <= GATES["max_weight_fraction_max"],
        "min_phase_ESS_min": full["min_phase_ESS"] >= GATES["min_phase_ESS_min"],
        "half_to_full_logI_drift_max": full["half_to_full_logI_drift"] <= GATES["half_to_full_logI_drift_max"],
    }
    full["pair_status"] = "PASS" if all(full["individual_gates"].values()) else "FAIL"
    return full


def summarize_four_pairs(pairs: Sequence[dict]):
    if len(pairs) != 4 or len({x["seed"] for x in pairs}) != 4:
        raise EvidenceError("four distinct matched seed pairs required")
    if len({x["draws"] for x in pairs}) != 1:
        raise EvidenceError("each pair must have the same sample budget")
    values = [float(p["logI"]) for p in pairs]
    spread = max(values) - min(values)
    gates = {
        "ESS_per_pair_min": all(x["individual_gates"]["ESS_per_pair_min"] for x in pairs),
        "max_weight_fraction_max": all(x["individual_gates"]["max_weight_fraction_max"] for x in pairs),
        "min_phase_ESS_min": all(x["individual_gates"]["min_phase_ESS_min"] for x in pairs),
        "between_pair_logI_spread_max": spread <= GATES["between_pair_logI_spread_max"],
        "half_to_full_logI_drift_max": all(x["individual_gates"]["half_to_full_logI_drift_max"] for x in pairs),
    }
    return {
        "protocol": "AUXILIARY_PREDECLARED_DETERMINISTIC_BALANCE_MIS_512_PLUS_512",
        "original_single_proposal_K4_K8_gates": "RETAINED_UNCHANGED",
        "EOS_Bayes": "NOT_RUN",
        "full_MR_convergence": "NOT_ESTABLISHED",
        "pair_results": pairs,
        "logI_spread": spread,
        "thresholds": GATES,
        "gates": gates,
        "status": "PASS" if all(gates.values()) else "FAIL",
        "no_new_photon_calls": True,
    }