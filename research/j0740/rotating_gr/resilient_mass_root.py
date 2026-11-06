"""Bisection robust to isolated upstream RNS numerical non-convergence.

Accept only physical mass/spin-validated RNS models returned by run_rns.
Failed density evaluations are recorded; never interpolate failed models.
"""
from __future__ import annotations

import math
import subprocess

class NumericalRootError(RuntimeError):
    """A reproducible RNS mass root could not be certified."""


def resilient_mass_root(eval_model, target: float, lo: float, hi: float,
                        *, tolerance: float = 0.0015, max_iterations: int = 32,
                        max_evaluations: int = 140):
    if not (math.isfinite(target) and 0.5 < target < 3.5
            and math.isfinite(lo) and math.isfinite(hi) and 0 < lo < hi
            and 0.0005 <= tolerance < 0.01):
        raise ValueError("invalid fixed-mass bracket or tolerance")
    trace = []
    evaluations = 0

    def measured(ec):
        nonlocal evaluations
        evaluations += 1
        try:
            output = eval_model(ec)
            mass = float(output["mass_msun"])
            radius = float(output["radius_eq_km"])
            if not (math.isfinite(mass) and math.isfinite(radius)
                    and 0 < mass < 4 and 6 < radius < 30):
                raise ValueError("nonfinite or implausible RNS result")
            trace.append({"rho": ec, "mass": mass, "radius": radius, "status": "OK"})
            return output
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            trace.append({"rho": ec, "status": "REJECTED",
                          "exception": type(exc).__name__,
                          "reason": str(exc)[:350]})
            return None

    left = measured(lo)
    right = measured(hi)
    if left is None or right is None:
        raise NumericalRootError("RNS root bracket endpoint failed; inspect scan data")
    lm, rm = float(left["mass_msun"]), float(right["mass_msun"])
    if not lm < target < rm:
        raise ValueError("stable increasing-mass bracket does not contain target")

    for _ in range(max_iterations):
        if evaluations >= max_evaluations:
            break
        width = hi - lo
        frac = min(0.9, max(0.1, (target-lm)/(rm-lm)))
        fractions = (frac, .5, .382, .618, .25, .75, .1, .9)
        accepted = False
        tried = set()
        for f in fractions:
            ec = lo + f * width
            key = round(f, 9)
            if key in tried or not lo < ec < hi:
                continue
            tried.add(key)
            if evaluations >= max_evaluations:
                break
            model = measured(ec)
            if model is None:
                continue
            mass = float(model["mass_msun"])
            # Reject suspicious non-monotonic stable branch instead of
            # manipulating mass to force convergence.
            if not lm - 0.002 <= mass <= rm + 0.002:
                raise NumericalRootError("non-monotone rotating stellar branch in sampled bracket")
            if abs(mass-target) <= tolerance:
                return model, trace
            if mass < target:
                lo, left, lm = ec, model, mass
            else:
                hi, right, rm = ec, model, mass
            accepted = True
            break
        if not accepted:
            break
    summary = f"no certified root within {tolerance} Msun after {evaluations} evaluations; " \
              f"bracket={lo:.7e},{hi:.7e}; masses={lm},{rm}; rejected={sum(p['status']=='REJECTED' for p in trace)}"
    raise NumericalRootError(summary)
