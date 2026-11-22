#!/usr/bin/env python3
"""F120 repeats three F119 fixed-J densities on an independent finer native RNS mesh."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from scipy.optimize import brentq

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

F119_ZIP_SHA = "e81516e53df76329e5abdb7141757a4d1a92d02c13e38d2eaa5afa395e91993c"
F118_ZIP_SHA = "f2f6b5609abac0c194c76ea06e2cdb4c770224102bbad7579d5cdb475aa4732c"
F119_RESULT = "F119/F119_FINE_INTRADENSITY_FIXEDJ_SCAN.json"
F119_JOURNAL = "F119/F119_FINE_INTRADENSITY_FIXEDJ_SCAN.jsonl"
F118_RESULT = "F118/F118_INTRADENSITY_FIXEDJ_SCAN.json"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
BASE_GRID = "2501x5001"
GRID = "3001x6001"
RHO_POINTS = (2622286500000000, 2622286750000000, 2622287000000000)
RATIO_BRACKET_HALF_WIDTH = 1.0e-4

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_f119(path: Path):
    archive_bytes = path.read_bytes()
    if sha(archive_bytes) != F119_ZIP_SHA:
        raise ValueError("F119_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F119_ARTIFACT_ZIP_CRC_FAILURE")
        result = json.loads(archive.read(F119_RESULT))
        journal_bytes = archive.read(F119_JOURNAL)
        f118_bytes = archive.read("F118/F118_artifact.zip")
    if sha(f118_bytes) != F118_ZIP_SHA:
        raise ValueError("F119_NESTED_F118_SHA256_MISMATCH")
    if sha(journal_bytes) != result.get("raw_journal_sha256"):
        raise ValueError("F119_RAW_JOURNAL_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines() if line.strip()]
    if (result.get("status") != "F119_FINE_INTRADENSITY_SCAN_COMPLETE"
            or result.get("diagnostic_only") is not True
            or result.get("mesh") != BASE_GRID
            or result.get("EOS_sha256") != EOS_SHA
            or result.get("target_J_cgs") != f106.TARGET_J
            or result.get("J_relative_tolerance") != f106.J_REL_TOL
            or result.get("pinned_RNS_upstream_commit") != RNS_COMMIT
            or result.get("native_C_call_count") != 25
            or len(rows) != 25
            or len(result.get("fixed_J_solutions", [])) != 5
            or result.get("native_C_errors")):
        raise ValueError("F119_BASELINE_NOT_ACCEPTED")
    if any(row.get("mesh") != BASE_GRID or row.get("real_native_RNS_C") is not True
           or row.get("error") for row in rows):
        raise ValueError("F119_RAW_ROW_INVALID")
    expected = (2622285500000000, 2622286000000000, 2622286500000000,
                2622287000000000, 2622287500000000)
    solutions = sorted(result["fixed_J_solutions"], key=lambda row: row["rho_g_cm3"])
    if tuple(int(row["rho_g_cm3"]) for row in solutions) != expected:
        raise ValueError("F119_DENSITY_BASELINE_MISMATCH")
    for solution in solutions:
        match = [row for row in rows
                 if row.get("rho_g_cm3") == solution["rho_g_cm3"]
                 and row.get("r_ratio_C_input") == solution["selected_r_ratio"]
                 and row.get("M_msun") == solution["M_msun"]
                 and row.get("J_relative_error") == solution["J_relative_error"]]
        if not match or solution.get("J_relative_error", 1.0) > f106.J_REL_TOL:
            raise ValueError("F119_ROOT_NOT_PRESENT_IN_NATIVE_JOURNAL")
    with zipfile.ZipFile(io.BytesIO(f118_bytes)) as nested:
        if nested.testzip() is not None:
            raise ValueError("NESTED_F118_ZIP_CRC_FAILURE")
        f118 = json.loads(nested.read(F118_RESULT))
    if (f118.get("status") != "F118_INTRADENSITY_FIXEDJ_SCAN_COMPLETE"
            or f118.get("diagnostic_only") is not True
            or f118.get("EOS_sha256") != EOS_SHA
            or f118.get("mesh") != BASE_GRID):
        raise ValueError("NESTED_F118_BASELINE_NOT_ACCEPTED")
    return result, rows

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f119", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    baseline, _ = read_f119(args.f119)
    if sha(args.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not args.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")
    bsol = {int(row["rho_g_cm3"]): row for row in baseline["fixed_J_solutions"]}
    low, high = bsol[RHO_POINTS[0]], bsol[RHO_POINTS[-1]]
    def center_ratio(rho: int) -> float:
        return low["selected_r_ratio"] + (rho-low["rho_g_cm3"]) * (
            high["selected_r_ratio"]-low["selected_r_ratio"]) / (
            high["rho_g_cm3"]-low["rho_g_cm3"])
    journal = args.out.with_suffix(".jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F120_RAW_FIXEDJ_JOURNAL")
    trial_rows, solutions, errors = [], [], []
    with journal.open("x", encoding="utf-8") as stream:
        for rho in RHO_POINTS:
            center = center_ratio(rho)
            bracket = (center-RATIO_BRACKET_HALF_WIDTH, center+RATIO_BRACKET_HALF_WIDTH)
            cache: dict[str, dict] = {}
            def evaluate(ratio: float) -> float:
                ratio_input = float(f"{ratio:.12f}")
                key = f"{ratio_input:.12f}"
                if key not in cache:
                    star = f106.call_rns(args.rns, args.eos, rho, ratio_input)
                    signed = star["J_cgs"]/f106.TARGET_J-1.0
                    row = {
                        "index": len(trial_rows), "rho_g_cm3": rho,
                        "r_ratio_C_input": ratio_input, "M_msun": star["M_msun"],
                        "R_eq_km": star["R_equatorial_km"], "f_hz": star["spin_hz"],
                        "J_cgs": star["J_cgs"], "J_signed_relative_error": signed,
                        "J_relative_error": abs(signed),
                        "within_target_tolerance": abs(signed) <= f106.J_REL_TOL,
                        "mesh": GRID, "real_native_RNS_C": True,
                    }
                    cache[key] = row
                    stream.write(json.dumps(row, sort_keys=True, allow_nan=False)+"\n")
                    stream.flush()
                    trial_rows.append(row)
                    print("F120_NATIVE_C_FIXEDJ_TRIAL", json.dumps(row, sort_keys=True), flush=True)
                return cache[key]["J_signed_relative_error"]
            try:
                lo, hi = sorted(bracket)
                f_lo, f_hi = evaluate(lo), evaluate(hi)
                if abs(f_lo) > f106.J_REL_TOL and abs(f_hi) > f106.J_REL_TOL:
                    if f_lo*f_hi >= 0:
                        raise RuntimeError("F120_FINE_MESH_J_BRACKET_NOT_FOUND")
                    root = brentq(evaluate, lo, hi, xtol=1e-10, rtol=5e-13, maxiter=70)
                    evaluate(root)
                accepted = min(cache.values(), key=lambda row: row["J_relative_error"])
                if accepted["J_relative_error"] > f106.J_REL_TOL:
                    raise RuntimeError("F120_FINE_MESH_J_TOLERANCE_FAIL")
                reference = bsol[rho]
                solutions.append({
                    "rho_g_cm3": rho, "selected_r_ratio": accepted["r_ratio_C_input"],
                    "M_msun": accepted["M_msun"], "R_eq_km": accepted["R_eq_km"],
                    "f_hz": accepted["f_hz"], "J_cgs": accepted["J_cgs"],
                    "J_relative_error": accepted["J_relative_error"],
                    "native_C_evaluations": len(cache), "real_native_RNS_C": True,
                    "mesh": GRID, "baseline_mesh": BASE_GRID,
                    "F119_baseline_M_msun": reference["M_msun"],
                    "F119_baseline_R_eq_km": reference["R_eq_km"],
                    "mesh_delta_M_msun": accepted["M_msun"]-reference["M_msun"],
                    "mesh_delta_R_eq_km": accepted["R_eq_km"]-reference["R_eq_km"],
                    "baseline_ratio_center": center, "local_ratio_bracket": [lo, hi],
                })
            except Exception as exc:
                errors.append({"rho_g_cm3": rho, "error": repr(exc),
                               "native_C_evaluations": len(cache),
                               "local_ratio_bracket": list(bracket)})
                print("F120_FIXEDJ_POINT_FAIL_RETAINED",
                      json.dumps(errors[-1], sort_keys=True), flush=True)
    solutions.sort(key=lambda row: row["rho_g_cm3"])
    mass_steps = []
    mesh_comparisons = []
    for row in solutions:
        mesh_comparisons.append({
            "rho_g_cm3": row["rho_g_cm3"],
            "F119_M_msun": row["F119_baseline_M_msun"],
            "F120_M_msun": row["M_msun"],
            "delta_M_msun": row["mesh_delta_M_msun"],
            "F119_R_eq_km": row["F119_baseline_R_eq_km"],
            "F120_R_eq_km": row["R_eq_km"],
            "delta_R_eq_km": row["mesh_delta_R_eq_km"],
        })
    if len(solutions) == len(RHO_POINTS):
        for a, b in zip(solutions, solutions[1:]):
            dm = b["M_msun"]-a["M_msun"]
            f119_dm = b["F119_baseline_M_msun"]-a["F119_baseline_M_msun"]
            mass_steps.append({
                "rho_low_g_cm3": a["rho_g_cm3"], "rho_high_g_cm3": b["rho_g_cm3"],
                "F119_mass_delta_msun": f119_dm, "F120_mass_delta_msun": dm,
                "mass_delta_change_msun": dm-f119_dm,
                "F120_to_F119_mass_delta_ratio": dm/f119_dm if f119_dm else None,
            })
    status = ("F120_FINE_MESH_DIAGNOSTIC_COMPLETE"
              if len(solutions) == len(RHO_POINTS) and not errors else "FAIL_CLOSED")
    out = {
        "schema": "J0740_F120_NATIVE_C_FINE_MESH_FIXEDJ_V1", "status": status,
        "diagnostic_only": True, "mesh": GRID, "baseline_mesh": BASE_GRID,
        "EOS_sha256": EOS_SHA, "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL, "pinned_RNS_upstream_commit": RNS_COMMIT,
        "input_F119_artifact_sha256": F119_ZIP_SHA, "input_F119_status": baseline["status"],
        "density_points_g_cm3": list(RHO_POINTS), "native_C_call_count": len(trial_rows),
        "trial_rows": trial_rows, "fixed_J_solutions": solutions,
        "mass_steps": mass_steps, "mesh_comparisons": mesh_comparisons,
        "native_C_errors": errors, "raw_journal_sha256": sha(journal.read_bytes()),
        "interpretation": (
            "Three fixed-J points on a finer RNS mesh compare the localized feature with F119. "
            "Two meshes are a sensitivity check, not formal convergence; these results do not "
            "establish physical cause, branch identity, a physical maximum, rotating-star stability, "
            "or photon-native EOS evidence."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print("F120_RESULT", json.dumps({k: out[k] for k in (
        "status", "native_C_call_count", "fixed_J_solutions", "mass_steps",
        "mesh_comparisons", "native_C_errors")}, sort_keys=True), flush=True)
    if status != "F120_FINE_MESH_DIAGNOSTIC_COMPLETE":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
