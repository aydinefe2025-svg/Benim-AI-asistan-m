#!/usr/bin/env python3
"""F113 re-solves the F111 bracket at fixed J on the 1001x2001 RNS mesh."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sys
import zipfile
from pathlib import Path
from scipy.optimize import brentq

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

F112_ZIP_SHA = "a3e05996d0896c42ce9229631f1139f1630ba473455e15ff56b0267e8925f681"
F111_ZIP_SHA = "55dea39f39070c891a67d776656ead97888641f048892befb3b3080e134bf29f"
F112_RESULT = "F112/F112_HIGH_GRID_MASS_STEP_CROSSCHECK.json"
F112_JOURNAL = "F112/F112_HIGH_GRID_MASS_STEP_CROSSCHECK.jsonl"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
GRID = "1001x2001"
RHO_TICKS_1E10 = (262228, 262229)
RATIO_SCAN = (0.999, 0.995, 0.990)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_f112(path: Path):
    raw = path.read_bytes()
    if sha(raw) != F112_ZIP_SHA:
        raise ValueError("F112_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F112_ARTIFACT_ZIP_CRC_FAILURE")
        result = json.loads(archive.read(F112_RESULT))
        journal_bytes = archive.read(F112_JOURNAL)
        f111_bytes = archive.read("F111/F111_artifact.zip")
    if sha(f111_bytes) != F111_ZIP_SHA:
        raise ValueError("F112_NESTED_F111_BASELINE_SHA256_MISMATCH")
    if sha(journal_bytes) != result.get("raw_journal_sha256"):
        raise ValueError("F112_RAW_JOURNAL_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines()]
    if (result.get("status") != "F112_HIGH_GRID_CROSSCHECK_COMPLETE"
            or result.get("diagnostic_only") is not True
            or result.get("low_grid") != "501x1001"
            or result.get("high_grid") != GRID
            or result.get("EOS_sha256") != EOS_SHA
            or result.get("target_J_cgs") != f106.TARGET_J
            or result.get("J_relative_tolerance") != f106.J_REL_TOL
            or result.get("pinned_RNS_upstream_commit") != RNS_COMMIT
            or result.get("input_F111_artifact_sha256") != F111_ZIP_SHA
            or result.get("new_native_C_point_count") != 4
            or result.get("new_native_C_call_count") != 4
            or result.get("native_C_errors")
            or len(rows) != 4):
        raise ValueError("F112_BASELINE_NOT_ACCEPTED")
    if any(row.get("mesh") != GRID or not row.get("real_native_RNS_C") for row in rows):
        raise ValueError("F112_HIGH_GRID_RAW_ROW_INVALID")
    return result, rows

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f112", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    baseline, _ = read_f112(args.f112)
    if sha(args.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not args.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")
    journal = args.out.with_suffix(".jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F113_RAW_FIXEDJ_JOURNAL")
    all_rows, solutions, errors = [], [], []
    with journal.open("x", encoding="utf-8") as stream:
        for rho_tick in RHO_TICKS_1E10:
            rho = rho_tick * 1e10
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
                    print("F113_NATIVE_C_FIXEDJ_TRIAL", json.dumps(row, sort_keys=True), flush=True)
                return cache[key]["J_signed_relative_error"]
            try:
                prior = None
                bracket = None
                chosen = None
                for ratio in RATIO_SCAN:
                    value = evaluate(ratio)
                    if abs(value) <= f106.J_REL_TOL:
                        chosen = ratio
                        break
                    if prior is not None and prior[1] * value < 0:
                        bracket = (prior[0], ratio)
                        break
                    prior = (ratio, value)
                if chosen is None:
                    if bracket is None:
                        raise RuntimeError("HIGH_GRID_FIXEDJ_SIGN_CHANGE_BRACKET_NOT_FOUND")
                    chosen = brentq(evaluate, *sorted(bracket), xtol=1e-10,
                                    rtol=5e-13, maxiter=60)
                    evaluate(chosen)
                accepted = min(cache.values(), key=lambda row: row["J_relative_error"])
                if accepted["J_relative_error"] > f106.J_REL_TOL:
                    raise RuntimeError("HIGH_GRID_FIXEDJ_ROOT_TOLERANCE_FAIL")
                solutions.append({
                    "rho_tick_1e10_g_cm3": rho_tick, "rho_g_cm3": rho,
                    "selected_r_ratio": accepted["r_ratio_C_input"],
                    "M_msun": accepted["M_msun"], "R_eq_km": accepted["R_eq_km"],
                    "f_hz": accepted["f_hz"], "J_cgs": accepted["J_cgs"],
                    "J_relative_error": accepted["J_relative_error"],
                    "native_C_evaluations": len(cache), "real_native_RNS_C": True,
                    "mesh": GRID,
                })
            except Exception as exc:
                errors.append({"rho_g_cm3": rho, "rho_tick_1e10_g_cm3": rho_tick,
                               "error": repr(exc), "native_C_evaluations": len(cache)})
                print("F113_FIXEDJ_POINT_FAIL_RETAINED",
                      json.dumps(errors[-1], sort_keys=True), flush=True)
    delta = None
    if len(solutions) == 2:
        solutions.sort(key=lambda row: row["rho_g_cm3"])
        delta = solutions[1]["M_msun"] - solutions[0]["M_msun"]
    status = ("F113_HIGH_GRID_FIXEDJ_ROOTS_COMPLETE"
              if len(solutions) == 2 and not errors else "FAIL_CLOSED")
    out = {
        "schema": "J0740_F113_NATIVE_C_FIXEDJ_HIGH_GRID_ROOTS_V1",
        "status": status, "diagnostic_only": True, "mesh": GRID,
        "EOS_sha256": EOS_SHA, "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL, "pinned_RNS_upstream_commit": RNS_COMMIT,
        "input_F112_artifact_sha256": F112_ZIP_SHA,
        "input_F112_status": baseline["status"],
        "density_ticks_1e10_g_cm3": list(RHO_TICKS_1E10),
        "ratio_scan": list(RATIO_SCAN),
        "new_native_C_call_count": len(all_rows), "trial_rows": all_rows,
        "fixed_J_solutions": solutions, "mass_difference_across_bracket_msun": delta,
        "native_C_errors": errors, "raw_journal_sha256": sha(journal.read_bytes()),
        "interpretation": (
            "Two selected fixed-J roots on a finer mesh do not prove branch identity, "
            "continuum/grid convergence, dynamical stability, a global physical "
            "maximum, or photon-native EOS evidence."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8")
    print("F113_RESULT", json.dumps({
        "status": status, "native_C_call_count": len(all_rows),
        "fixed_J_solutions": solutions,
        "mass_difference_across_bracket_msun": delta,
        "native_C_errors": errors,
    }, sort_keys=True), flush=True)
    if status != "F113_HIGH_GRID_FIXEDJ_ROOTS_COMPLETE":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
