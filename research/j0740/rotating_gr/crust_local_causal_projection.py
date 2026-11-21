"""Fail-closed local *diagnostic* for a sampled JESTER crust reversal.

Five preexisting source-neighborhood points 252..256 are used to calculate
how much e[253], e[254] would need to move in a **hypothetical new** table
for the *sampled pressure/energy secants* to satisfy 0 < dP/de <= cap.

Crucial limitations: this is NOT a repaired LALSuite EOS, NOT continuous
sound-speed certification, NOT thermodynamic h(P)/n(P) consistency, NOT an
RNS/TOV recomputation, and NOT Bayesian EOS model evidence. Source untouched.
"""
from __future__ import annotations
import math
from typing import Any


class LocalProjectionNotFeasible(ValueError):
    """The limited 2-node repair cannot meet all fixed-anchor inequalities."""


def project_local_five_nodes(neighborhood: list[dict[str, Any]], cap: float = 0.95) -> dict:
    """Euclidean-minimal two-node e correction if solely edge 253->254 fails.

    Fix e_252, e_255, e_256 and all pressures. The active constraint is
    e'_254-e'_253 = (p_254-p_253)/cap. Orthogonal projection onto this
    halfspace shifts e_253 by -Delta/2 and e_254 by +Delta/2.

    If any other edge is initially noncausal, or the projected solution
    violates an anchored neighbor, fail closed; do not pretend this limited
    closed-form solution is a general thermodynamic projection.
    """
    if len(neighborhood) != 5 or not (math.isfinite(cap) and 0 < cap <= 1):
        raise ValueError("Expected five original nodes and a physical 0<cap<=1")
    index = [n["index"] for n in neighborhood]
    if index != [252, 253, 254, 255, 256]:
        raise ValueError("This diagnostic accepts exactly source indices 252..256")
    p = [float(n["p_geom_m_minus2"]) for n in neighborhood]
    e = [float(n["energy_geom_m_minus2"]) for n in neighborhood]
    if not all(math.isfinite(a) and a > 0 for a in p + e):
        raise ValueError("Nonfinite or nonpositive source thermodynamic node")
    if any(p[i + 1] <= p[i] for i in range(4)):
        raise ValueError("Source pressure not strictly increasing")

    def secants(array):
        return [(p[i + 1] - p[i]) / (array[i + 1] - array[i])
                if array[i + 1] != array[i] else math.inf for i in range(4)]

    old = secants(e)
    # Tolerance is for float64 at source-data precision, not a physical margin.
    tol = 2e-12
    invalid_edges = [i for i, v in enumerate(old) if not (math.isfinite(v) and 0 < v <= cap * (1 + tol))]
    if any(i != 1 for i in invalid_edges):
        raise LocalProjectionNotFeasible("Outside center 253->254 edge fails; fixed-neighbor 2-node method not applicable")

    projected = list(e)
    delta_required = max(0.0, (p[2] - p[1]) / cap - (e[2] - e[1]))
    if delta_required > 0:
        projected[1] -= delta_required / 2.0
        projected[2] += delta_required / 2.0
    after = secants(projected)
    if any(not (math.isfinite(v) and 0 < v <= cap * (1 + 1e-9)) for v in after):
        raise LocalProjectionNotFeasible("Balanced least-squares correction violates fixed adjacent edge")
    if any(projected[i] != e[i] for i in (0, 3, 4)):
        raise AssertionError("Anchor source value changed")
    if not all(math.isfinite(x) and x > 0 for x in projected):
        raise LocalProjectionNotFeasible("Projection makes energy nonphysical")
    changed = bool(delta_required > 0)
    rel = [abs(a - b) / b for a, b in zip(projected, e)]
    return {
        "scope": "diagnostic_local_secants_only_not_physical_eos",
        "cs2_cap_requested": cap,
        "source_indices": index,
        "source_p_geom": p,
        "source_e_geom": e,
        "candidate_e_geom": projected,
        "original_secant_cs2_over_c2": old,
        "candidate_secant_cs2_over_c2": after,
        "modified_source_indices": [253, 254] if changed else [],
        "total_required_e254_minus_e253_increase_geom": delta_required,
        "absolute_energy_shift_each_geom": delta_required / 2.,
        "maximum_relative_energy_adjustment": max(rel),
        "source_analytic_cs2_at_knot": neighborhood[2].get("cs2_native"),
        "original_native_negative_derivative_removed": False,
        "full_eos_physics_validated": False,
        "reason": "Constrained two-node least-squares bound only; source analytic dp/de, continuous EOS, n(P), h(P), and RNS/TOV must be recomputed on an explicitly NEW source model",
    }
