#!/usr/bin/env python3
"""F115 solves the same two fixed-J roots on a fourth, finer RNS grid."""
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

F114_ZIP_SHA = "20832bfcf5c10fa401f9292ab9a11a3d41596de1afe275e4ae2ffb62e0f21755"
F113_ZIP_SHA = "6ccf9096a0d9d341b9f0b51b5aeb60b0b2a8129113a26e9c81463602ed6c4b01"
F114_RESULT = "F114/F114_THIRD_GRID_FIXEDJ_ROOTS.json"
F114_JOURNAL = "F114/F114_THIRD_GRID_FIXEDJ_ROOTS.jsonl"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
PREVIOUS_GRID = "1501x3001"
GRID = "2001x4001"
RHO_TICKS_1E10 = (262228, 262229)
RATIO_BRACKET_HALF_WIDTH = 2.5e-5

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_f114(path: Path):
    raw = path.read_bytes()
    if sha(raw) != F114_ZIP_SHA:
        raise ValueError("F114_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F114_ARTIFACT_ZIP_CRC_FAILURE")
        result = json.loads(archive.read(F114_RESULT))
        journal_bytes = archive.read(F114_JOURNAL)
        f113_bytes = archive.read("F113/F113_artifact.zip")
    if sha(f113_bytes) != F113_ZIP_SHA:
        raise ValueError("F114_NESTED_F113_BASELINE_SHA256_MISMATCH")
    if sha(journal_bytes) != result.get("raw_journal_sha256"):
        raise ValueError("F114_RAW_JOURNAL_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines()]
    if (result.get("status") != "F114_THIRD_GRID_FIXEDJ_ROOTS_COMPLETE"
            or result.get("diagnostic_only") is not True
            or result.get("mesh") != PREVIOUS_GRID
            or result.get("EOS_sha256") != EOS_SHA
            or result.get("target_J_cgs") != f106.TARGET_J
            or result.get("J_relative_tolerance") != f106.J_REL_TOL
            or result.get("pinned_RNS_upstream_commit") != RNS_COMMIT
            or result.get("input_F113_artifact_sha256") != F113_ZIP_SHA
            or result.get("new_native_C_call_count") != 14
            or len(rows) != 14
            or len(result.get("fixed_J_solutions", [])) != 2
            or result.get("native_C_errors")):
        raise ValueError("F114_BASELINE_NOT_ACCEPTED")
    if any(row.get("mesh") != PREVIOUS_GRID or not row.get("real_native_RNS_C") for row in rows):
        raise ValueError("F114_RAW_ROW_INVALID")
    return result, rows

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f114", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    baseline, _ = read_f114(args.f114)
    if sha(args.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not args.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")
    previous = {row["rho_tick_1e10_g_cm3"]: row
                for row in baseline["fixed_J_solutions"]}
    if any(tick not in previous for tick in RHO_TICKS_1E10):
        raise ValueError("F114_PREVIOUS_GRID_DENSITIES_MISSING")
    journal = args.out.with_suffix(".jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F115_RAW_FIXEDJ_JOURNAL")
    all_rows, solutions, errors = [], [], []
    with journal.open("x", encoding="utf-8") as stream:
        for rho_tick in RHO_TICKS_1E10:
            rho = rho_tick * 1e10
            center = previous[rho_tick]["selected_r_ratio"]
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
                    print("F115_NATIVE_C_FIXEDJ_TRIAL", json.dumps(row, sort_keys=True), flush=True)
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
                    raise RuntimeError("FOURTH_GRID_FIXEDJ_LOCAL_BRACKET_NOT_FOUND")
                accepted = min(cache.values(), key=lambda row: row["J_relative_error"])
                if accepted["J_relative_error"] > f106.J_REL_TOL:
                    raise RuntimeError("FOURTH_GRID_FIXEDJ_ROOT_TOLERANCE_FAIL")
                solutions.append({
                    "rho_tick_1e10_g_cm3": rho_tick, "rho_g_cm3": rho,
                    "selected_r_ratio": accepted["r_ratio_C_input"],
                    "M_msun": accepted["M_msun"], "R_eq_km": accepted["R_eq_km"],
                    "f_hz": accepted["f_hz"], "J_cgs": accepted["J_cgs"],
                    "J_relative_error": accepted["J_relative_error"],
                    "native_C_evaluations": len(cache), "real_native_RNS_C": True,
                    "mesh": GRID,
                    "previous_grid_r_ratio": center,
                    "previous_grid_M_msun": previous[rho_tick]["M_msun"],
                    "previous_grid_J_relative_error": previous[rho_tick]["J_relative_error"],
                    "local_ratio_bracket": [low, high],
                })
            except Exception as exc:
                errors.append({"rho_g_cm3": rho, "rho_tick_1e10_g_cm3": rho_tick,
                               "error": repr(exc), "native_C_evaluations": len(cache),
                               "local_ratio_bracket": list(bracket)})
                print("F115_FIXEDJ_POINT_FAIL_RETAINED",
                      json.dumps(errors[-1], sort_keys=True), flush=True)
    solutions.sort(key=lambda row: row["rho_g_cm3"])
    mass_delta = solutions[1]["M_msun"] - solutions[0]["M_msun"] if len(solutions) == 2 else None
    previous_delta = (previous[RHO_TICKS_1E10[1]]["M_msun"]
                      - previous[RHO_TICKS_1E10[0]]["M_msun"])
    status = ("F115_FOURTH_GRID_FIXEDJ_ROOTS_COMPLETE"
              if len(solutions) == 2 and not errors else "FAIL_CLOSED")
    out = {
        "schema": "J0740_F115_NATIVE_C_FOURTH_GRID_FIXEDJ_ROOTS_V1",
        "status": status, "diagnostic_only": True,
        "previous_grid": PREVIOUS_GRID, "mesh": GRID,
        "EOS_sha256": EOS_SHA, "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL,
        "pinned_RNS_upstream_commit": RNS_COMMIT,
        "input_F114_artifact_sha256": F114_ZIP_SHA,
        "input_F114_status": baseline["status"],
        "density_ticks_1e10_g_cm3": list(RHO_TICKS_1E10),
        "ratio_bracket_half_width": RATIO_BRACKET_HALF_WIDTH,
        "new_native_C_call_count": len(all_rows), "trial_rows": all_rows,
        "fixed_J_solutions": solutions,
        "mass_difference_across_bracket_msun": mass_delta,
        "previous_grid_mass_difference_msun": previous_delta,
        "native_C_errors": errors, "raw_journal_sha256": sha(journal.read_bytes()),
        "interpretation": (
            "A fourth-grid two-point fixed-J comparison still does not establish "
            "continuum convergence, branch identity, a physical maximum, dynamical "
            "stability, or photon-native EOS evidence."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8")
    print("F115_RESULT", json.dumps({
        "status": status, "native_C_call_count": len(all_rows),
        "fixed_J_solutions": solutions,
        "mass_difference_across_bracket_msun": mass_delta,
        "previous_grid_mass_difference_msun": previous_delta,
        "native_C_errors": errors,
    }, sort_keys=True), flush=True)
    if status != "F115_FOURTH_GRID_FIXEDJ_ROOTS_COMPLETE":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
