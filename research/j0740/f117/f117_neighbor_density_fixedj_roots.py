#!/usr/bin/env python3
"""F117 solves two neighboring-density fixed-J roots on the existing fifth RNS grid."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from scipy.optimize import brentq

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

F116_ZIP_SHA = "2947996a32d1db249830faa6014f7a75ebfd913c1edde98acaad074742d91f7d"
F115_ZIP_SHA = "f6e4d4a6d11bfde5647e63206081d774613e0d2278d726dd8c237b245b2f352f"
F116_RESULT = "F116/F116_FIFTH_GRID_FIXEDJ_ROOTS.json"
F116_JOURNAL = "F116/F116_FIFTH_GRID_FIXEDJ_ROOTS.jsonl"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
PREVIOUS_GRID = "2501x5001"
GRID = "2501x5001"
RHO_TICKS_1E10 = (262227, 262230)
RATIO_BRACKET_HALF_WIDTH = 2.5e-5

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_f116(path: Path):
    raw = path.read_bytes()
    if sha(raw) != F116_ZIP_SHA:
        raise ValueError("F116_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F116_ARTIFACT_ZIP_CRC_FAILURE")
        result = json.loads(archive.read(F116_RESULT))
        journal_bytes = archive.read(F116_JOURNAL)
        f115_bytes = archive.read("F115/F115_artifact.zip")
    if sha(f115_bytes) != F115_ZIP_SHA:
        raise ValueError("F116_NESTED_F115_BASELINE_SHA256_MISMATCH")
    if sha(journal_bytes) != result.get("raw_journal_sha256"):
        raise ValueError("F116_RAW_JOURNAL_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines()]
    if (result.get("status") != "F116_FIFTH_GRID_FIXEDJ_ROOTS_COMPLETE"
            or result.get("diagnostic_only") is not True
            or result.get("mesh") != PREVIOUS_GRID
            or result.get("EOS_sha256") != EOS_SHA
            or result.get("target_J_cgs") != f106.TARGET_J
            or result.get("J_relative_tolerance") != f106.J_REL_TOL
            or result.get("pinned_RNS_upstream_commit") != RNS_COMMIT
            or result.get("input_F115_artifact_sha256") != F115_ZIP_SHA
            or result.get("new_native_C_call_count") != 10
            or len(rows) != 10
            or len(result.get("fixed_J_solutions", [])) != 2
            or result.get("native_C_errors")):
        raise ValueError("F116_BASELINE_NOT_ACCEPTED")
    if any(row.get("mesh") != PREVIOUS_GRID or not row.get("real_native_RNS_C") for row in rows):
        raise ValueError("F116_RAW_ROW_INVALID")
    return result, rows

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f116", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    baseline, _ = read_f116(args.f116)
    if sha(args.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not args.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")
    previous = {row["rho_tick_1e10_g_cm3"]: row
                for row in baseline["fixed_J_solutions"]}
    baseline_ticks = sorted(previous)
    if baseline_ticks != [262228, 262229]:
        raise ValueError("F116_BASELINE_DENSITY_PAIR_MISMATCH")
    def baseline_linear(field: str, rho_tick: int) -> float:
        low_tick, high_tick = baseline_ticks
        low_value = previous[low_tick][field]
        high_value = previous[high_tick][field]
        return low_value + (rho_tick-low_tick) * (high_value-low_value) / (high_tick-low_tick)
    journal = args.out.with_suffix(".jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F117_RAW_FIXEDJ_JOURNAL")
    all_rows, solutions, errors = [], [], []
    with journal.open("x", encoding="utf-8") as stream:
        for rho_tick in RHO_TICKS_1E10:
            rho = rho_tick * 1e10
            center = baseline_linear("selected_r_ratio", rho_tick)
            bracket = (center - RATIO_BRACKET_HALF_WIDTH,
                       center + RATIO_BRACKET_HALF_WIDTH)
            cache: dict[str, dict] = {}
            def evaluate(ratio: float) -> float:
                ratio_input = float(f"{ratio:.12f}")
                key = f"{ratio_input:.12f}"
                if key not in cache:
                    star = f106.call_rns(args.rns, args.eos, rho, ratio_input)
                    signed = star["J_cgs"] / f106.TARGET_J - 1.0
                    row = {
                        "index": len(all_rows), "rho_tick_1e10_g_cm3": rho_tick,
                        "rho_g_cm3": rho, "r_ratio_C_input": ratio_input,
                        "M_msun": star["M_msun"], "R_eq_km": star["R_equatorial_km"],
                        "f_hz": star["spin_hz"], "J_cgs": star["J_cgs"],
                        "J_signed_relative_error": signed,
                        "J_relative_error": abs(signed),
                        "within_target_tolerance": abs(signed) <= f106.J_REL_TOL,
                        "mesh": GRID, "real_native_RNS_C": True,
                    }
                    cache[key] = row
                    stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                    stream.flush()
                    all_rows.append(row)
                    print("F117_NATIVE_C_FIXEDJ_TRIAL", json.dumps(row, sort_keys=True), flush=True)
                return cache[key]["J_signed_relative_error"]
            try:
                low, high = sorted(bracket)
                f_low, f_high = evaluate(low), evaluate(high)
                if abs(f_low) <= f106.J_REL_TOL or abs(f_high) <= f106.J_REL_TOL:
                    pass
                elif f_low * f_high < 0:
                    root = brentq(evaluate, low, high, xtol=1e-10,
                                  rtol=5e-13, maxiter=60)
                    evaluate(root)
                else:
                    raise RuntimeError("NEIGHBOR_DENSITY_FIXEDJ_LOCAL_BRACKET_NOT_FOUND")
                accepted = min(cache.values(), key=lambda row: row["J_relative_error"])
                if accepted["J_relative_error"] > f106.J_REL_TOL:
                    raise RuntimeError("NEIGHBOR_DENSITY_FIXEDJ_ROOT_TOLERANCE_FAIL")
                solutions.append({
                    "rho_tick_1e10_g_cm3": rho_tick, "rho_g_cm3": rho,
                    "selected_r_ratio": accepted["r_ratio_C_input"],
                    "M_msun": accepted["M_msun"], "R_eq_km": accepted["R_eq_km"],
                    "f_hz": accepted["f_hz"], "J_cgs": accepted["J_cgs"],
                    "J_relative_error": accepted["J_relative_error"],
                    "native_C_evaluations": len(cache), "real_native_RNS_C": True,
                    "mesh": GRID,
                    "baseline_linear_r_ratio_center": center,
                    "baseline_linear_M_msun": baseline_linear("M_msun", rho_tick),
                    "ratio_bracket_center_source": "linear extrapolation from F116 adjacent roots",
                    "local_ratio_bracket": [low, high],
                })
            except Exception as exc:
                errors.append({"rho_g_cm3": rho, "rho_tick_1e10_g_cm3": rho_tick,
                               "error": repr(exc), "native_C_evaluations": len(cache),
                               "local_ratio_bracket": list(bracket)})
                print("F117_FIXEDJ_POINT_FAIL_RETAINED",
                      json.dumps(errors[-1], sort_keys=True), flush=True)
    solutions.sort(key=lambda row: row["rho_g_cm3"])
    mass_delta = solutions[1]["M_msun"] - solutions[0]["M_msun"] if len(solutions) == 2 else None
    baseline_inner_delta = (previous[262229]["M_msun"] - previous[262228]["M_msun"])
    average_outer_delta_per_tick = mass_delta / 3.0 if mass_delta is not None else None
    average_outer_slope_change_percent = (
        100.0 * (average_outer_delta_per_tick / baseline_inner_delta - 1.0)
        if average_outer_delta_per_tick is not None and baseline_inner_delta != 0.0 else None)
    status = ("F117_NEIGHBOR_DENSITY_FIXEDJ_ROOTS_COMPLETE"
              if len(solutions) == 2 and not errors else "FAIL_CLOSED")
    out = {
        "schema": "J0740_F117_NATIVE_C_NEIGHBOR_DENSITY_FIXEDJ_ROOTS_V1",
        "status": status, "diagnostic_only": True,
        "previous_grid": PREVIOUS_GRID, "mesh": GRID,
        "EOS_sha256": EOS_SHA, "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL,
        "pinned_RNS_upstream_commit": RNS_COMMIT,
        "input_F116_artifact_sha256": F116_ZIP_SHA,
        "input_F116_status": baseline["status"],
        "density_ticks_1e10_g_cm3": list(RHO_TICKS_1E10),
        "ratio_bracket_half_width": RATIO_BRACKET_HALF_WIDTH,
        "new_native_C_call_count": len(all_rows), "trial_rows": all_rows,
        "fixed_J_solutions": solutions,
        "mass_difference_across_bracket_msun": mass_delta,
        "baseline_inner_mass_difference_msun": baseline_inner_delta,
        "average_outer_mass_difference_per_tick_msun": average_outer_delta_per_tick,
        "average_outer_slope_change_percent": average_outer_slope_change_percent,
        "native_C_errors": errors, "raw_journal_sha256": sha(journal.read_bytes()),
        "interpretation": (
            "A neighbor-density two-point fixed-J comparison still does not establish "
            "continuum convergence, branch identity, a physical maximum, dynamical "
            "stability, or photon-native EOS evidence."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8")
    print("F117_RESULT", json.dumps({
        "status": status, "native_C_call_count": len(all_rows),
        "fixed_J_solutions": solutions,
        "mass_difference_across_bracket_msun": mass_delta,
        "baseline_inner_mass_difference_msun": baseline_inner_delta,
        "average_outer_mass_difference_per_tick_msun": average_outer_delta_per_tick,
        "average_outer_slope_change_percent": average_outer_slope_change_percent,
        "native_C_errors": errors,
    }, sort_keys=True), flush=True)
    if status != "F117_NEIGHBOR_DENSITY_FIXEDJ_ROOTS_COMPLETE":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
