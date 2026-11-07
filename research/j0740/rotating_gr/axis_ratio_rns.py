"""Independent fixed-density RNS axis-ratio spin refinement.

The pinned rns-alberta/rns C solver supports -r (axis ratio). Its original
SetSpin helper uses float Ridder iterates and may leave measurable spin
residuals. When -s is outside a strictly bounded frequency tolerance, solve
for an actually computed -r model at the requested spin. Every accepted
model must be a *real C solver solution*, never an interpolated mass/radius.
"""
from __future__ import annotations

import math
from pathlib import Path
import subprocess

from rns_benchmark import OBSERVED_SPIN_HZ, parse_rns_output, run_rns


class AxisRatioConvergenceError(RuntimeError):
    def __init__(self, message: str, *, trace=None):
        super().__init__(message)
        self.trace = list(trace or [])


def run_rns_at_ratio(binary: Path, eos_file: Path, *,
                     central_density: float, ratio: float,
                     timeout: int = 180) -> dict:
    if not (math.isfinite(ratio) and 0.75 <= ratio <= 1.0):
        raise ValueError("RNS axis ratio outside physically guarded interval")
    if not (math.isfinite(central_density) and central_density > 0):
        raise ValueError("Invalid central energy density")
    eos_arg = "./" + eos_file.name
    if len(eos_arg.encode("utf-8")) >= 80:
        raise ValueError("RNS EOS basename exceeds upstream C char[80] limit")
    proc = subprocess.run(
        [str(binary.resolve()), "-f", eos_arg, "-e",
         f"{central_density:.12g}", "-r", f"{ratio:.10f}"],
        cwd=str(eos_file.resolve().parent),
        text=True, capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"RNS -r process exit {proc.returncode}: {proc.stderr[-700:]}")
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        try:
            nums = [float(v) for v in parts]
        except ValueError:
            continue
        if all(math.isfinite(n) for n in nums):
            rows.append(nums)
    if len(rows) != 1:
        raise ValueError("RNS -r emitted no unique finite physical model")
    reported_freq = rows[0][3]
    if reported_freq < 0 or reported_freq >= 1000:
        raise ValueError("RNS axis-ratio model rotation outside accepted frequency domain")
    model = parse_rns_output(proc.stdout,
                             central_density=central_density,
                             requested_spin_hz=reported_freq)
    model["axis_ratio"] = ratio
    model["solver_mode"] = "RNS_C_AXIS_RATIO_DIRECT"
    return model


def axis_ratio_spin_root(eval_model, target_hz: float, *,
                         tolerance_hz: float = 0.10, max_evaluations: int = 38):
    if not (math.isfinite(target_hz) and 0 < target_hz < 1000
            and 0 < tolerance_hz <= .10 and 10 <= max_evaluations <= 60):
        raise ValueError("invalid RNS axis-ratio spin root settings")
    history = []
    calls = 0

    def evaluate(r):
        nonlocal calls
        if calls >= max_evaluations:
            return None
        calls += 1
        try:
            model = eval_model(r)
            hz = float(model["spin_hz_reported"])
            if not math.isfinite(hz) or hz < 0 or hz > 1000:
                raise ValueError("invalid or nonphysical RNS spin")
            history.append({"axis_ratio": r, "spin_hz": hz,
                            "mass_msun": float(model["mass_msun"]),
                            "radius_eq_km": float(model["radius_eq_km"]),
                            "status": "OK"})
            return model
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            history.append({"axis_ratio": r, "status": "REJECTED",
                            "reason": f"{type(exc).__name__}: {str(exc)[:180]}"})
            return None

    static = evaluate(1.0)
    if static is None or abs(float(static["spin_hz_reported"])) > .1:
        raise AxisRatioConvergenceError("RNS -r static control invalid",trace=history)
    slow_r, slow_f = 1.0, float(static["spin_hz_reported"])
    fast_r = None
    for k in range(1, 21):
        ratio=1.0-k*.01
        m = evaluate(ratio)
        if m is None:
            continue
        hz=float(m["spin_hz_reported"])
        if hz < slow_f-1.0:
            raise AxisRatioConvergenceError("Nonmonotone axis-ratio spin sequence", trace=history)
        if abs(hz-target_hz)<=tolerance_hz:
            return m,history
        if hz>=target_hz:
            fast_r=ratio
            break
        slow_r,slow_f=ratio,hz

    if fast_r is None:
        raise AxisRatioConvergenceError("Requested spin not bracketed before axis-ratio floor 0.8", trace=history)

    for _ in range(26):
        if calls>=max_evaluations:
            break
        accepted=False
        for frac in (0.5, 0.382, 0.618):
            r = slow_r + frac*(fast_r-slow_r)
            if not fast_r < r < slow_r:
                continue
            m = evaluate(r)
            if m is None:
                continue
            hz=float(m["spin_hz_reported"])
            if abs(hz-target_hz)<=tolerance_hz:
                return m,history
            if hz < target_hz:
                slow_r,slow_f=r,hz
            else:
                fast_r=r
            accepted=True
            break
        if not accepted:
            break
    raise AxisRatioConvergenceError(
        f"No direct RNS -r solution within {tolerance_hz} Hz after {calls} trials",
        trace=history)


def run_rns_at_spin_with_ratio_fallback(binary: Path, eos_file: Path, *,
                                        central_density: float,
                                        spin_hz: float = OBSERVED_SPIN_HZ) -> dict:
    try:
        model = run_rns(binary,eos_file,central_density=central_density,
                        spin_hz=spin_hz,spin_tolerance_hz=.25)
        model["solver_mode"] = "RNS_C_SETSPIN"
        return model
    except ValueError as exc:
        if "Rotating GR spin mismatch" not in str(exc):
            raise
    model,trace=axis_ratio_spin_root(
        lambda r: run_rns_at_ratio(binary,eos_file,
                                   central_density=central_density,ratio=r),
        spin_hz)
    model["requested_spin_hz"] = spin_hz
    model["spin_residual_hz"] = model["spin_hz_reported"] - spin_hz
    model["allowed_spin_residual_hz"] = .10
    model["solver_mode"] = "RNS_C_AXIS_RATIO_FREQUENCY_REFINED"
    model["axis_ratio_bisection_trace"] = trace
    return model
