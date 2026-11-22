#!/usr/bin/env python3
"""F121 bisects F120's upper-half fixed-J mass feature at the same fine mesh."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from scipy.optimize import brentq

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106
from research.j0740.f120 import f120_fine_mesh_fixedj as f120

F120_ZIP_SHA = "e92b83d2e3297e09a3db81526bece5e86f05ab14628a534901e04ce8884531a2"
F119_ZIP_SHA = "e81516e53df76329e5abdb7141757a4d1a92d02c13e38d2eaa5afa395e91993c"
F120_RESULT = "F120/F120_FINE_MESH_FIXEDJ.json"
F120_JOURNAL = "F120/F120_FINE_MESH_FIXEDJ.jsonl"
F119_RESULT = "F119/F119_FINE_INTRADENSITY_FIXEDJ_SCAN.json"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
GRID = "3001x6001"
LOW_RHO = 2622286750000000
HIGH_RHO = 2622287000000000
MID_RHO = 2622286875000000
RATIO_BRACKET_HALF_WIDTH = 1.0e-6
DIAGNOSTIC_ROOT_TOLERANCE = 1.0e-9

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_f120(path: Path):
    raw = path.read_bytes()
    if sha(raw) != F120_ZIP_SHA:
        raise ValueError("F120_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F120_ARTIFACT_ZIP_CRC_FAILURE")
        result = json.loads(archive.read(F120_RESULT))
        journal_bytes = archive.read(F120_JOURNAL)
        f119_bytes = archive.read("F119/F119_artifact.zip")
    if sha(f119_bytes) != F119_ZIP_SHA:
        raise ValueError("F120_NESTED_F119_SHA256_MISMATCH")
    if sha(journal_bytes) != result.get("raw_journal_sha256"):
        raise ValueError("F120_RAW_JOURNAL_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines() if line.strip()]
    if (result.get("status") != "F120_FINE_MESH_DIAGNOSTIC_COMPLETE"
            or result.get("diagnostic_only") is not True
            or result.get("mesh") != GRID
            or result.get("baseline_mesh") != "2501x5001"
            or result.get("EOS_sha256") != EOS_SHA
            or result.get("target_J_cgs") != f106.TARGET_J
            or result.get("J_relative_tolerance") != f106.J_REL_TOL
            or result.get("pinned_RNS_upstream_commit") != RNS_COMMIT
            or result.get("native_C_call_count") != 18
            or len(rows) != 18
            or len(result.get("fixed_J_solutions", [])) != 3
            or result.get("native_C_errors")):
        raise ValueError("F120_BASELINE_NOT_ACCEPTED")
    if any(row.get("mesh") != GRID or row.get("real_native_RNS_C") is not True
           or row.get("error") for row in rows):
        raise ValueError("F120_RAW_ROW_INVALID")
    roots = sorted(result["fixed_J_solutions"], key=lambda row: row["rho_g_cm3"])
    expected = (2622286500000000, LOW_RHO, HIGH_RHO)
    if tuple(int(root["rho_g_cm3"]) for root in roots) != expected:
        raise ValueError("F120_DENSITY_ROOTS_MISMATCH")
    for root in roots:
        candidates = [row for row in rows if row["rho_g_cm3"] == root["rho_g_cm3"]]
        if len(candidates) != 6:
            raise ValueError("F120_TRIAL_COUNT_PER_ROOT_MISMATCH")
        best = min(candidates, key=lambda row: row["J_relative_error"])
        if any(root.get(a) != best[b] for a, b in (
                ("M_msun", "M_msun"), ("R_eq_km", "R_eq_km"),
                ("J_relative_error", "J_relative_error"),
                ("selected_r_ratio", "r_ratio_C_input"))):
            raise ValueError("F120_ROOT_NOT_PRESENT_IN_RAW_JOURNAL")
        if best["J_relative_error"] > f106.J_REL_TOL:
            raise ValueError("F120_ROOT_OUTSIDE_TARGET_J_TOLERANCE")
    with zipfile.ZipFile(io.BytesIO(f119_bytes)) as nested:
        if nested.testzip() is not None:
            raise ValueError("NESTED_F119_ZIP_CRC_FAILURE")
        f119 = json.loads(nested.read(F119_RESULT))
    if f119.get("status") != "F119_FINE_INTRADENSITY_SCAN_COMPLETE":
        raise ValueError("NESTED_F119_BASELINE_NOT_ACCEPTED")
    return result, rows

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f120", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    baseline, _ = read_f120(args.f120)
    if sha(args.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not args.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")

    roots = {int(row["rho_g_cm3"]): row for row in baseline["fixed_J_solutions"]}
    low, high = roots[LOW_RHO], roots[HIGH_RHO]
    fraction = (MID_RHO-LOW_RHO)/(HIGH_RHO-LOW_RHO)
    center = low["selected_r_ratio"] + fraction*(
        high["selected_r_ratio"]-low["selected_r_ratio"])
    bracket = (center-RATIO_BRACKET_HALF_WIDTH, center+RATIO_BRACKET_HALF_WIDTH)
    journal = args.out.with_suffix(".jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F121_RAW_FIXEDJ_JOURNAL")
    cache: dict[str, dict] = {}
    errors = []
    with journal.open("x", encoding="utf-8") as stream:
        def evaluate(ratio: float) -> float:
            ratio_input = float(f"{ratio:.12f}")
            key = f"{ratio_input:.12f}"
            if key not in cache:
                star = f106.call_rns(args.rns, args.eos, MID_RHO, ratio_input)
                signed = star["J_cgs"]/f106.TARGET_J-1.0
                row = {
                    "index": len(cache), "rho_g_cm3": MID_RHO,
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
                print("F121_NATIVE_C_FIXEDJ_TRIAL", json.dumps(row, sort_keys=True), flush=True)
            return cache[key]["J_signed_relative_error"]
        try:
            f_center = evaluate(center)
            if abs(f_center) > DIAGNOSTIC_ROOT_TOLERANCE:
                lo, hi = sorted(bracket)
                f_lo, f_hi = evaluate(lo), evaluate(hi)
                if abs(f_lo) > DIAGNOSTIC_ROOT_TOLERANCE and abs(f_hi) > DIAGNOSTIC_ROOT_TOLERANCE:
                    if f_lo*f_hi >= 0:
                        raise RuntimeError("F121_FIXEDJ_BRACKET_NOT_FOUND")
                    root = brentq(evaluate, lo, hi, xtol=1e-12, rtol=5e-14, maxiter=70)
                    evaluate(root)
            best = min(cache.values(), key=lambda row: row["J_relative_error"])
            if best["J_relative_error"] > DIAGNOSTIC_ROOT_TOLERANCE:
                raise RuntimeError("F121_FIXEDJ_DIAGNOSTIC_PRECISION_FAIL")
        except Exception as exc:
            errors.append({"rho_g_cm3": MID_RHO, "error": repr(exc),
                           "native_C_evaluations": len(cache),
                           "local_ratio_bracket": list(bracket)})
            print("F121_FIXEDJ_POINT_FAIL_RETAINED", json.dumps(errors[-1], sort_keys=True), flush=True)

    solutions = []
    if not errors and cache:
        best = min(cache.values(), key=lambda row: row["J_relative_error"])
        solutions.append({
            "rho_g_cm3": MID_RHO, "selected_r_ratio": best["r_ratio_C_input"],
            "M_msun": best["M_msun"], "R_eq_km": best["R_eq_km"],
            "f_hz": best["f_hz"], "J_cgs": best["J_cgs"],
            "J_relative_error": best["J_relative_error"],
            "native_C_evaluations": len(cache), "real_native_RNS_C": True,
            "mesh": GRID, "baseline_mesh": GRID,
            "baseline_low_rho_g_cm3": LOW_RHO, "baseline_low_M_msun": low["M_msun"],
            "baseline_high_rho_g_cm3": HIGH_RHO, "baseline_high_M_msun": high["M_msun"],
            "baseline_ratio_center": center, "local_ratio_bracket": list(sorted(bracket)),
        })
    mass_steps = []
    if len(solutions) == 1:
        mid = solutions[0]
        mass_steps = [
            {"rho_low_g_cm3": LOW_RHO, "rho_high_g_cm3": MID_RHO,
             "mass_delta_msun": mid["M_msun"]-low["M_msun"]},
            {"rho_low_g_cm3": MID_RHO, "rho_high_g_cm3": HIGH_RHO,
             "mass_delta_msun": high["M_msun"]-mid["M_msun"]},
        ]
    status = "F121_UPPER_HALF_BISECTION_COMPLETE" if len(solutions)==1 and not errors else "FAIL_CLOSED"
    out = {
        "schema": "J0740_F121_NATIVE_C_UPPER_HALF_BISECTION_V1",
        "status": status, "diagnostic_only": True, "mesh": GRID,
        "EOS_sha256": EOS_SHA, "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL,
        "diagnostic_root_tolerance": DIAGNOSTIC_ROOT_TOLERANCE,
        "pinned_RNS_upstream_commit": RNS_COMMIT,
        "input_F120_artifact_sha256": F120_ZIP_SHA,
        "input_F120_status": baseline["status"],
        "density_points_g_cm3": [LOW_RHO, MID_RHO, HIGH_RHO],
        "native_C_call_count": len(cache), "trial_rows": list(cache.values()),
        "fixed_J_solutions": solutions, "mass_steps": mass_steps,
        "native_C_errors": errors, "raw_journal_sha256": sha(journal.read_bytes()),
        "interpretation": (
            "One midpoint subdivides F120's sampled upper-half mass step. This is a density "
            "localization diagnostic on one mesh, not a physical cause, branch identity, formal "
            "mesh convergence, physical maximum, rotating-star stability, or photon-native EOS result."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print("F121_RESULT", json.dumps({k:out[k] for k in (
        "status","native_C_call_count","fixed_J_solutions","mass_steps","native_C_errors")},sort_keys=True),flush=True)
    if status != "F121_UPPER_HALF_BISECTION_COMPLETE":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
