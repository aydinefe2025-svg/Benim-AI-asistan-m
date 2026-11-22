#!/usr/bin/env python3
"""F122 bisects the lower half of F121's localized fixed-J mass step."""
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

F121_ZIP_SHA = "f601f6b3d449e7ef07a14e83fdfcaf3f1b027148c418cff252a670803af217e4"
F120_ZIP_SHA = "e92b83d2e3297e09a3db81526bece5e86f05ab14628a534901e04ce8884531a2"
F121_RESULT = "F121/F121_UPPER_HALF_BISECTION.json"
F121_JOURNAL = "F121/F121_UPPER_HALF_BISECTION.jsonl"
F120_RESULT = "F120/F120_FINE_MESH_FIXEDJ.json"
F119_RESULT = "F119/F119_FINE_INTRADENSITY_FIXEDJ_SCAN.json"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
GRID = "3001x6001"
LOW_RHO = 2622286750000000
HIGH_RHO = 2622286875000000
MID_RHO = 2622286812500000
DIAGNOSTIC_ROOT_TOLERANCE = 1.0e-9
RATIO_BRACKET_HALF_WIDTH = 1.0e-6

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_f121(path: Path):
    raw = path.read_bytes()
    if sha(raw) != F121_ZIP_SHA:
        raise ValueError("F121_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F121_ARTIFACT_ZIP_CRC_FAILURE")
        result = json.loads(archive.read(F121_RESULT))
        journal_bytes = archive.read(F121_JOURNAL)
        f120_bytes = archive.read("F120/F120_artifact.zip")
    if sha(f120_bytes) != F120_ZIP_SHA:
        raise ValueError("F121_NESTED_F120_SHA256_MISMATCH")
    if sha(journal_bytes) != result.get("raw_journal_sha256"):
        raise ValueError("F121_RAW_JOURNAL_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines() if line.strip()]
    if (result.get("status") != "F121_UPPER_HALF_BISECTION_COMPLETE"
            or result.get("diagnostic_only") is not True
            or result.get("mesh") != GRID
            or result.get("EOS_sha256") != EOS_SHA
            or result.get("target_J_cgs") != f106.TARGET_J
            or result.get("J_relative_tolerance") != f106.J_REL_TOL
            or result.get("diagnostic_root_tolerance") != DIAGNOSTIC_ROOT_TOLERANCE
            or result.get("pinned_RNS_upstream_commit") != RNS_COMMIT
            or result.get("input_F120_artifact_sha256") != F120_ZIP_SHA
            or result.get("native_C_call_count") != 6
            or len(rows) != 6
            or len(result.get("fixed_J_solutions", [])) != 1
            or result.get("native_C_errors")):
        raise ValueError("F121_BASELINE_NOT_ACCEPTED")
    if any(row.get("mesh") != GRID or row.get("real_native_RNS_C") is not True
           or row.get("error") for row in rows):
        raise ValueError("F121_RAW_ROW_INVALID")
    root = result["fixed_J_solutions"][0]
    if int(root.get("rho_g_cm3", -1)) != HIGH_RHO:
        raise ValueError("F121_MIDPOINT_DENSITY_MISMATCH")
    best = min(rows, key=lambda row: row["J_relative_error"])
    if any(root.get(a) != best.get(b) for a, b in (
            ("M_msun", "M_msun"), ("R_eq_km", "R_eq_km"),
            ("J_relative_error", "J_relative_error"),
            ("selected_r_ratio", "r_ratio_C_input"))):
        raise ValueError("F121_ROOT_NOT_PRESENT_IN_RAW_JOURNAL")
    if best["J_relative_error"] > DIAGNOSTIC_ROOT_TOLERANCE:
        raise ValueError("F121_ROOT_PRECISION_NOT_ACCEPTED")
    with tempfile.NamedTemporaryFile(suffix=".zip") as nested:
        nested.write(f120_bytes)
        nested.flush()
        f120_result, f120_rows = f120.read_f120(Path(nested.name))
    with zipfile.ZipFile(io.BytesIO(f120_bytes)) as archive:
        f119_bytes = archive.read("F119/F119_artifact.zip")
    if sha(f119_bytes) != f120.F119_ZIP_SHA:
        raise ValueError("F120_NESTED_F119_SHA256_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(f119_bytes)) as nested:
        if nested.testzip() is not None:
            raise ValueError("F119_NESTED_ZIP_CRC_FAILURE")
        f119_result = json.loads(nested.read(F119_RESULT))
    if f119_result.get("status") != "F119_FINE_INTRADENSITY_SCAN_COMPLETE":
        raise ValueError("F119_NESTED_BASELINE_NOT_ACCEPTED")
    return result, f120_result, f120_rows

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f121", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    f121_result, f120_result, _ = read_f121(args.f121)
    if sha(args.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not args.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")

    f120_roots = {int(row["rho_g_cm3"]): row for row in f120_result["fixed_J_solutions"]}
    f121_high = f121_result["fixed_J_solutions"][0]
    low = f120_roots[LOW_RHO]
    high = f121_high
    fraction = (MID_RHO-LOW_RHO)/(HIGH_RHO-LOW_RHO)
    center = low["selected_r_ratio"] + fraction*(
        high["selected_r_ratio"]-low["selected_r_ratio"])
    bracket = (center-RATIO_BRACKET_HALF_WIDTH, center+RATIO_BRACKET_HALF_WIDTH)
    journal = args.out.with_suffix(".jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F122_RAW_FIXEDJ_JOURNAL")
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
                    "within_diagnostic_precision": abs(signed) <= DIAGNOSTIC_ROOT_TOLERANCE,
                    "mesh": GRID, "real_native_RNS_C": True,
                }
                cache[key] = row
                stream.write(json.dumps(row, sort_keys=True, allow_nan=False)+"\n")
                stream.flush()
                print("F122_NATIVE_C_FIXEDJ_TRIAL", json.dumps(row, sort_keys=True), flush=True)
            return cache[key]["J_signed_relative_error"]
        try:
            f_center = evaluate(center)
            if abs(f_center) > DIAGNOSTIC_ROOT_TOLERANCE:
                lo, hi = sorted(bracket)
                f_lo, f_hi = evaluate(lo), evaluate(hi)
                if abs(f_lo) > DIAGNOSTIC_ROOT_TOLERANCE and abs(f_hi) > DIAGNOSTIC_ROOT_TOLERANCE:
                    if f_lo*f_hi >= 0:
                        raise RuntimeError("F122_FIXEDJ_BRACKET_NOT_FOUND")
                    root_ratio = brentq(evaluate, lo, hi, xtol=1e-12, rtol=5e-14, maxiter=70)
                    evaluate(root_ratio)
            best = min(cache.values(), key=lambda row: row["J_relative_error"])
            if best["J_relative_error"] > DIAGNOSTIC_ROOT_TOLERANCE:
                raise RuntimeError("F122_FIXEDJ_DIAGNOSTIC_PRECISION_FAIL")
        except Exception as exc:
            errors.append({"rho_g_cm3": MID_RHO, "error": repr(exc),
                           "native_C_evaluations": len(cache),
                           "local_ratio_bracket": list(bracket)})
            print("F122_FIXEDJ_POINT_FAIL_RETAINED", json.dumps(errors[-1], sort_keys=True), flush=True)

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
    status = "F122_LOWER_HALF_BISECTION_COMPLETE" if len(solutions)==1 and not errors else "FAIL_CLOSED"
    out = {
        "schema": "J0740_F122_NATIVE_C_LOWER_HALF_BISECTION_V1",
        "status": status, "diagnostic_only": True, "mesh": GRID,
        "EOS_sha256": EOS_SHA, "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL,
        "diagnostic_root_tolerance": DIAGNOSTIC_ROOT_TOLERANCE,
        "pinned_RNS_upstream_commit": RNS_COMMIT,
        "input_F121_artifact_sha256": F121_ZIP_SHA,
        "input_F121_status": f121_result["status"],
        "input_F120_artifact_sha256": F120_ZIP_SHA,
        "density_points_g_cm3": [LOW_RHO, MID_RHO, HIGH_RHO],
        "native_C_call_count": len(cache), "trial_rows": list(cache.values()),
        "fixed_J_solutions": solutions, "mass_steps": mass_steps,
        "native_C_errors": errors, "raw_journal_sha256": sha(journal.read_bytes()),
        "interpretation": (
            "One midpoint bisects F121's lower-half sampled mass step on the same mesh. "
            "This localizes the sampled feature only; it does not establish physical cause, branch "
            "identity, formal mesh convergence, a physical maximum, rotating-star stability, or "
            "photon-native EOS evidence."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print("F122_RESULT", json.dumps({k:out[k] for k in (
        "status","native_C_call_count","fixed_J_solutions","mass_steps","native_C_errors")},sort_keys=True),flush=True)
    if status != "F122_LOWER_HALF_BISECTION_COMPLETE":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
