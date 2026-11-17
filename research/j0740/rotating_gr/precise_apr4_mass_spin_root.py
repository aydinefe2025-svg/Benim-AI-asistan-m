"""Unrounded two-constraint RNS root for APR4_EPP (not EOS inference).

Uses the pinned upstream RNS solver and a diagnostic-only output precision
patch. The returned model is a direct C RNS solve, never an interpolated star.
The source n column is retained in this geometry run but M_b is explicitly
not interpreted because the native APR4 source n fails the first-law audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np

from jester_to_rns import DEFAULT_POINTS, from_jester_npz, write_rns

RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
JESTER_COMMIT = "e6768650ce992abfd1153a6833857572fe5cd230"
TARGET_MASS_MSUN = 2.073
TARGET_SPIN_HZ = 346.536369
MASS_TOL_MSUN = 1.0e-5
SPIN_TOL_HZ = 1.0e-4
WITHIN_GRID_SEED_RADIUS_TOL_KM = 1.0e-3
BETWEEN_GRID_RADIUS_TOL_KM = 2.0e-2

_OUTPUT_RE = re.compile(
    r'printf\("%g\s*\\t\s*%4\.3f\s*\\t\s*%4\.2f\s*\\t\s*%4\.1f\s*\\n",\s*'
    r'star\.e_center,\s*star\.Mass/MSUN,\s*star\.R_e\*1e-5,\s*'
    r'star\.Omega/\(2\.0\*PI\)\);'
)
_PATCHED_PRINT = (
    'printf("%.17g %.17g %.17g %.17g %.17g\\n",\n'
    '           star.e_center, star.Mass/MSUN, star.R_e*1e-5,\n'
    '           star.Omega/(2.0*PI), star.Mass_0/MSUN);'
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def patch_output_precision(source: Path) -> dict:
    """Change only the final diagnostic printf; reject upstream drift."""
    raw = source.read_bytes()
    old_sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
    text2, count = _OUTPUT_RE.subn(_PATCHED_PRINT, text)
    if count != 1:
        raise ValueError(f"expected one pinned RNS output row, found {count}")
    source.write_text(text2, encoding="utf-8", newline="\n")
    return {"upstream_source_sha256": old_sha,
            "patched_source_sha256": sha256(source),
            "replacement_count": count,
            "scope": "final printf format only; no solver arithmetic changed"}


def parse_output(stdout: str, center_g_cm3: float) -> dict:
    rows = []
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) != 5:
            continue
        try:
            row = [float(x) for x in fields]
        except ValueError:
            continue
        if all(math.isfinite(x) for x in row):
            rows.append(row)
    if len(rows) != 1:
        raise ValueError(f"RNS final row count={len(rows)}; stdout_tail={stdout[-1000:]!r}")
    ec_e15, mass, radius, spin, m0 = rows[0]
    if not (0.5 < mass < 3.5 and 6.0 < radius < 30.0
            and 0.0 <= spin < 2000.0 and 0.0 < m0 < 5.0):
        raise ValueError("RNS returned a nonphysical/nonfinite model")
    if not math.isclose(ec_e15, center_g_cm3 / 1e15, rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError(f"RNS central density mismatch: {ec_e15} vs {center_g_cm3/1e15}")
    return {"central_energy_density_g_cm3": center_g_cm3,
            "axis_ratio": None, "mass_msun": mass, "radius_eq_km": radius,
            "spin_hz": spin, "rns_M0_using_native_Mb_msun": m0}


def run_model(binary: Path, eos_file: Path, center_g_cm3: float,
              ratio: float, timeout: int = 180) -> dict:
    if not (math.isfinite(center_g_cm3) and 1.0e15 <= center_g_cm3 <= 2.5e15):
        raise ValueError("central density outside preregistered RNS bracket")
    if not (math.isfinite(ratio) and 0.80 <= ratio <= 1.0):
        raise ValueError("axis ratio outside preregistered physical bracket")
    arg = "./" + eos_file.name
    if len(arg.encode("ascii")) >= 80:
        raise ValueError("RNS filename exceeds upstream char[80] limit")
    proc = subprocess.run([str(binary.resolve()), "-f", arg, "-e",
                           f"{center_g_cm3:.12g}", "-r", f"{ratio:.10f}"],
                         cwd=eos_file.parent, capture_output=True, text=True,
                         timeout=timeout, check=False)
    if proc.returncode:
        raise RuntimeError(f"RNS exit={proc.returncode}; stderr={proc.stderr[-800:]!r}")
    model = parse_output(proc.stdout, center_g_cm3)
    model["axis_ratio"] = ratio
    return model


def _norm(residual: tuple[float, float]) -> float:
    # Balance dimensionless mass and spin residual scales for line search.
    return math.hypot(residual[0] / 1.0e-3, residual[1] / 1.0)


def solve_fixed_mf(evaluate, seed: tuple[float, float], *, max_iterations: int = 24):
    """Safeguarded 2-D Newton solve in (ec/1e15, r_ratio).

    The exact requested mass and spin are both residuals. Every failed direct
    RNS evaluation is retained in trace and no interpolation is allowed.
    """
    u, ratio = map(float, seed)
    if not (1.0 <= u <= 2.5 and .80 <= ratio <= 1.0):
        raise ValueError("seed outside preregistered root domain")
    trace: list[dict] = []

    class RootFailure(RuntimeError):
        def __init__(self, message):
            super().__init__(message)
            self.trace = list(trace)

    def call(xu, xr, label):
        try:
            model = evaluate(xu * 1e15, xr)
            mass, spin = float(model["mass_msun"]), float(model["spin_hz"])
            if not all(math.isfinite(v) for v in (mass, spin)):
                raise ValueError("non-finite physical output")
            residual = (mass - TARGET_MASS_MSUN, spin - TARGET_SPIN_HZ)
            model["central_energy_density_g_cm3"] = xu * 1e15
            model["axis_ratio"] = xr
            trace.append({"eval": label, "u_ec_1e15": xu, "axis_ratio": xr,
                          "mass_msun": mass, "spin_hz": spin,
                          "delta_mass_msun": residual[0], "delta_spin_hz": residual[1],
                          "status": "OK"})
            return model, residual
        except Exception as exc:
            trace.append({"eval": label, "u_ec_1e15": xu, "axis_ratio": xr,
                          "status": "FAILED", "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            return None, None

    model, res = call(u, ratio, "seed")
    if res is None:
        raise RootFailure("seed RNS model failed; see trace")
    for iteration in range(max_iterations):
        if abs(res[0]) <= MASS_TOL_MSUN and abs(res[1]) <= SPIN_TOL_HZ:
            model["root_seed"] = list(seed)
            model["root_trace"] = trace
            model["mass_residual_tolerance_msun"] = MASS_TOL_MSUN
            model["spin_residual_tolerance_hz"] = SPIN_TOL_HZ
            return model

        du = max(2.0e-5, abs(u) * 2.0e-5)
        dr = 2.0e-6
        mu, ru = call(u + du, ratio, f"jacobian_u_{iteration}")
        mr, rr = call(u, ratio + dr, f"jacobian_r_{iteration}")
        if ru is None or rr is None:
            raise RootFailure("finite-difference RNS Jacobian evaluation failed; see trace")
        a = ((ru[0] - res[0]) / du, (ru[1] - res[1]) / du)
        b = ((rr[0] - res[0]) / dr, (rr[1] - res[1]) / dr)
        det = a[0] * b[1] - b[0] * a[1]
        if not math.isfinite(det) or abs(det) < 1e-10:
            raise RootFailure(f"singular/nonfinite mass-spin Jacobian det={det}; see trace")
        step_u = (res[0] * b[1] - b[0] * res[1]) / det
        step_r = (a[0] * res[1] - res[0] * a[1]) / det

        accepted = None
        for backtrack in range(12):
            lam = 0.5 ** backtrack
            cu, cr = u - lam * step_u, ratio - lam * step_r
            if not (1.0 <= cu <= 2.5 and .80 <= cr <= 1.0):
                continue
            cm, cres = call(cu, cr, f"newton_{iteration}_bt{backtrack}")
            if cres is not None and _norm(cres) < _norm(res):
                accepted = (cu, cr, cm, cres)
                break
        if accepted is None:
            raise RootFailure("damped Newton made no residual progress; see trace")
        u, ratio, model, res = accepted
    raise RootFailure(f"2-D RNS root did not converge in {max_iterations} iterations; see trace")


def run_grid(binary: Path, eos_file: Path, seeds: list[tuple[float, float]]) -> dict:
    results, failures = [], []
    for seed in seeds:
        try:
            ans = solve_fixed_mf(lambda ec, r: run_model(binary, eos_file, ec, r), seed)
            results.append(ans)
        except Exception as exc:
            failures.append({"seed": list(seed), "status": "FAILED",
                             "error": f"{type(exc).__name__}: {str(exc)[:600]}",
                             "trace": getattr(exc, "trace", [])})
    seed_match = (len(results) == len(seeds) and
                  abs(results[0]["mass_msun"] - results[1]["mass_msun"]) <= MASS_TOL_MSUN and
                  abs(results[0]["spin_hz"] - results[1]["spin_hz"]) <= SPIN_TOL_HZ and
                  abs(results[0]["radius_eq_km"] - results[1]["radius_eq_km"]) <= WITHIN_GRID_SEED_RADIUS_TOL_KM)
    return {"grid": binary.name, "seeds": results, "failures": failures,
            "independent_seed_agreement_pass": bool(seed_match)}


def run(args) -> dict:
    source, rns_source = args.source, args.rns_source
    if sha256(source) != args.expected_npz_sha256:
        raise ValueError("pinned APR4_EPP NPZ SHA256 mismatch")
    patch = json.loads(args.patch_metadata.read_text(encoding="utf-8"))
    if patch.get("patched_source_sha256") != sha256(rns_source):
        raise ValueError("built RNS source does not match diagnostic precision patch record")
    rows, convert_meta = from_jester_npz(source, points=args.points)
    # The source n column is not first-law consistent. This experiment is
    # limited to M_g, R_eq and frequency; it records but does not infer M_b.
    table = args.work / "APR4_EPP_precise_root.rns"
    write_rns(table, rows)
    grid_results = [run_grid(b, table, [(1.75, .960), (1.80, .965)]) for b in args.binary]
    all_pass = len(grid_results) == 2 and all(g["independent_seed_agreement_pass"] for g in grid_results)
    if all_pass:
        a, b = [g["seeds"][0] for g in grid_results]
        between = {"delta_mass_msun": b["mass_msun"] - a["mass_msun"],
                   "delta_spin_hz": b["spin_hz"] - a["spin_hz"],
                   "delta_radius_km": b["radius_eq_km"] - a["radius_eq_km"],
                   "delta_central_density_g_cm3": b["central_energy_density_g_cm3"] - a["central_energy_density_g_cm3"],
                   "radius_tolerance_km": BETWEEN_GRID_RADIUS_TOL_KM}
        between["pass"] = abs(between["delta_radius_km"]) <= BETWEEN_GRID_RADIUS_TOL_KM
    else:
        between = {"pass": False, "reason": "one or more same-grid independent roots failed"}
    return {
        "schema": "j0740-apr4-precise-rns-fixed-mass-spin-v1",
        "status": "PASS_CONDITIONAL_RNS_ROOT" if all_pass and between["pass"] else "FAILED_OR_PARTIAL_ROOT",
        "targets": {"mass_msun": TARGET_MASS_MSUN, "spin_hz": TARGET_SPIN_HZ,
                    "mass_tolerance_msun": MASS_TOL_MSUN, "spin_tolerance_hz": SPIN_TOL_HZ},
        "sources": {"rns_commit": RNS_COMMIT, "jester_commit": JESTER_COMMIT,
                    "rns_c_original_sha256": patch["upstream_source_sha256"],
                    "rns_c_diagnostic_printf_sha256": patch["patched_source_sha256"],
                    "rns_print_patch": patch,
                    "apr4_npz_sha256": sha256(source), "apr4_npz_bytes": source.stat().st_size,
                    "rns_eos_table_sha256": sha256(table), "rns_eos_table_bytes": table.stat().st_size},
        "eos_table": {"points": args.points, "conversion": convert_meta,
                      "baryon_column": "native JESTER n retained for audit compatibility; M_b is not interpreted because first-law source-n gate fails; M_g/R_eq/f are the outputs under test"},
        "method": "Direct RNS C runs at (central energy density, axis ratio), safeguarded 2-D Newton; two independent starting seeds per spatial mesh; no interpolation of stellar outputs",
        "spatial_grids": grid_results, "between_grid": between,
        "acceptance": {"all_four_roots_pass": bool(all_pass and between["pass"]),
                       "physical_eos_certification": "NOT_ESTABLISHED",
                       "EOS_Bayes": "NOT_RUN"}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--rns-source", type=Path, required=True)
    p.add_argument("--binary", type=Path, nargs=2, required=True)
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--patch-metadata", type=Path, required=True)
    p.add_argument("--points", type=int, default=DEFAULT_POINTS)
    p.add_argument("--expected-npz-sha256", required=True)
    p.add_argument("--patch-only", action="store_true")
    a = p.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    if a.patch_only:
        patch = patch_output_precision(a.rns_source)
        a.patch_metadata.parent.mkdir(parents=True, exist_ok=True)
        a.patch_metadata.write_text(json.dumps(patch, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        print(json.dumps(patch, indent=2, sort_keys=True))
        return
    result = run(a)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "targets", "sources", "between_grid", "acceptance")}, indent=2))
    if result["status"] != "PASS_CONDITIONAL_RNS_ROOT":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

