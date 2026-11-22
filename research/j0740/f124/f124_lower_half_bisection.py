#!/usr/bin/env python3
"""F124 bisects the remaining lower-half F123 fixed-J sampled mass step."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from scipy.optimize import brentq

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106
from research.j0740.f120 import f120_fine_mesh_fixedj as f120
from research.j0740.f123 import f123_lower_half_bisection as f123

F123_ZIP_SHA = "923e0fb508ecb7a4733ed5cc3da62834ba4caf4b4e4ed396ad29e229874d281f"
F122_ZIP_SHA = "73a0d50b394264312a467fd40b9f0d96f66a7786f54a1103c2fd458327fb3c0f"
F123_RESULT = "F123/F123_LOWER_HALF_BISECTION.json"
F123_JOURNAL = "F123/F123_LOWER_HALF_BISECTION.jsonl"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
GRID = "3001x6001"
LOW_RHO = 2622286750000000
HIGH_RHO = 2622286781250000
MID_RHO = 2622286765625000
DIAGNOSTIC_ROOT_TOLERANCE = 1.0e-9
RATIO_BRACKET_HALF_WIDTH = 1.0e-6
RNS_TIMEOUT_SECONDS = 600

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def call_rns_bounded(binary: Path, eos: Path, rho: float, ratio: float) -> dict:
    sys.path.insert(0, str(REPO_ROOT / "research/j0740/f81"))
    from f81_exact_mass_spin import parse_rns
    command = [str(binary.resolve()), "-f", str(eos), "-e", f"{rho:.14e}", "-r", f"{ratio:.12f}"]
    process = subprocess.run(command, capture_output=True, text=True, timeout=RNS_TIMEOUT_SECONDS)
    if process.returncode != 0:
        raise RuntimeError("RNS_NATIVE_C_FAILED " + process.stdout[-240:] + process.stderr[-240:])
    star = parse_rns(process.stdout)
    if abs(star["rho_c_g_cm3"]/rho-1.0) > 1.0e-9:
        raise ValueError("NATIVE_C_CENTRAL_DENSITY_MISMATCH")
    return star

def read_f123(path: Path):
    raw = path.read_bytes()
    if sha(raw) != F123_ZIP_SHA:
        raise ValueError("F123_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F123_ARTIFACT_ZIP_CRC_FAILURE")
        result = json.loads(archive.read(F123_RESULT))
        journal_bytes = archive.read(F123_JOURNAL)
        f122_bytes = archive.read("F122/F122_artifact.zip")
    if sha(f122_bytes) != F122_ZIP_SHA:
        raise ValueError("F123_NESTED_F122_SHA256_MISMATCH")
    if sha(journal_bytes) != result.get("raw_journal_sha256"):
        raise ValueError("F123_RAW_JOURNAL_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines() if line.strip()]
    if (result.get("status") != "F123_LOWER_HALF_BISECTION_COMPLETE"
            or result.get("diagnostic_only") is not True
            or result.get("mesh") != GRID
            or result.get("EOS_sha256") != EOS_SHA
            or result.get("target_J_cgs") != f106.TARGET_J
            or result.get("J_relative_tolerance") != f106.J_REL_TOL
            or result.get("diagnostic_root_tolerance") != DIAGNOSTIC_ROOT_TOLERANCE
            or result.get("pinned_RNS_upstream_commit") != RNS_COMMIT
            or result.get("input_F122_artifact_sha256") != F122_ZIP_SHA
            or result.get("native_C_call_count") != 6
            or len(rows) != 6
            or len(result.get("fixed_J_solutions", [])) != 1
            or result.get("native_C_errors")):
        raise ValueError("F123_BASELINE_NOT_ACCEPTED")
    if any(row.get("mesh") != GRID or row.get("real_native_RNS_C") is not True
           or row.get("error") for row in rows):
        raise ValueError("F123_RAW_ROW_INVALID")
    root = result["fixed_J_solutions"][0]
    if int(root.get("rho_g_cm3", -1)) != HIGH_RHO:
        raise ValueError("F123_MIDPOINT_DENSITY_MISMATCH")
    best = min(rows, key=lambda row: row["J_relative_error"])
    if any(root.get(a) != best.get(b) for a, b in (
            ("M_msun", "M_msun"), ("R_eq_km", "R_eq_km"),
            ("J_relative_error", "J_relative_error"),
            ("selected_r_ratio", "r_ratio_C_input"))):
        raise ValueError("F123_ROOT_NOT_PRESENT_IN_RAW_JOURNAL")
    if best["J_relative_error"] > DIAGNOSTIC_ROOT_TOLERANCE:
        raise ValueError("F123_ROOT_PRECISION_NOT_ACCEPTED")
    with tempfile.NamedTemporaryFile(suffix=".zip") as nested:
        nested.write(f122_bytes)
        nested.flush()
        f122_result, f121_result, f120_result, f120_rows = f123.read_f122(Path(nested.name))
    if f122_result.get("status") != "F122_LOWER_HALF_BISECTION_COMPLETE":
        raise ValueError("NESTED_F122_BASELINE_NOT_ACCEPTED")
    return result, f122_result, f121_result, f120_result, f120_rows

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f123", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    f123_result, f122_result, f121_result, f120_result, _ = read_f123(args.f123)
    if sha(args.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not args.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")

    f120_roots = {int(row["rho_g_cm3"]): row for row in f120_result["fixed_J_solutions"]}
    low = f120_roots[LOW_RHO]
    high = f123_result["fixed_J_solutions"][0]
    fraction = (MID_RHO-LOW_RHO)/(HIGH_RHO-LOW_RHO)
    center = low["selected_r_ratio"] + fraction*(high["selected_r_ratio"]-low["selected_r_ratio"])
    bracket = (center-RATIO_BRACKET_HALF_WIDTH, center+RATIO_BRACKET_HALF_WIDTH)
    journal = args.out.with_suffix(".jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F124_RAW_FIXEDJ_JOURNAL")
    cache: dict[str, dict] = {}
    errors = []
    rejected_trials = []
    with journal.open("x", encoding="utf-8") as stream:
        def evaluate(ratio: float) -> float:
            ratio_input = float(f"{ratio:.12f}")
            key = f"{ratio_input:.12f}"
            if key not in cache:
                star = call_rns_bounded(args.rns, args.eos, MID_RHO, ratio_input)
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
                print("F124_NATIVE_C_FIXEDJ_TRIAL", json.dumps(row, sort_keys=True), flush=True)
            return cache[key]["J_signed_relative_error"]
        seed_candidates = [high["selected_r_ratio"], low["selected_r_ratio"], center]
        for seed_ratio in seed_candidates:
            try:
                evaluate(seed_ratio)
            except Exception as exc:
                rejected_trials.append({"r_ratio_C_input": seed_ratio, "error": repr(exc)})
                print("F124_NATIVE_C_SEED_REJECTED", json.dumps(rejected_trials[-1], sort_keys=True), flush=True)
            if cache and min(row["J_relative_error"] for row in cache.values()) <= DIAGNOSTIC_ROOT_TOLERANCE:
                break

        def sign_brackets():
            ordered = sorted(cache.values(), key=lambda row: row["r_ratio_C_input"])
            return [(a, b) for a, b in zip(ordered, ordered[1:])
                    if a["J_signed_relative_error"]*b["J_signed_relative_error"] < 0.0]

        if not cache or min(row["J_relative_error"] for row in cache.values()) > DIAGNOSTIC_ROOT_TOLERANCE:
            if not sign_brackets():
                for bound in sorted(bracket):
                    key = f"{float(f'{bound:.12f}'):.12f}"
                    if key not in cache:
                        try:
                            evaluate(bound)
                        except Exception as exc:
                            rejected_trials.append({"r_ratio_C_input": bound, "error": repr(exc)})
                            print("F124_NATIVE_C_BOUND_REJECTED", json.dumps(rejected_trials[-1], sort_keys=True), flush=True)
                    if sign_brackets():
                        break
            pairs = sign_brackets()
            if pairs:
                lo_row, hi_row = pairs[0]
                root_ratio = brentq(evaluate, lo_row["r_ratio_C_input"], hi_row["r_ratio_C_input"],
                                    xtol=1e-12, rtol=5e-14, maxiter=70)
                evaluate(root_ratio)
            elif cache:
                errors.append({"rho_g_cm3": MID_RHO, "error": "F124_FIXEDJ_BRACKET_NOT_FOUND",
                               "native_C_evaluations": len(cache),
                               "local_ratio_bracket": list(bracket)})
            elif not cache:
                errors.append({"rho_g_cm3": MID_RHO, "error": "F124_NO_NATIVE_C_EVALUATION_COMPLETED",
                               "native_C_evaluations": 0,
                               "local_ratio_bracket": list(bracket)})
        if cache and min(row["J_relative_error"] for row in cache.values()) > DIAGNOSTIC_ROOT_TOLERANCE:
            if not errors:
                errors.append({"rho_g_cm3": MID_RHO, "error": "F124_FIXEDJ_DIAGNOSTIC_PRECISION_FAIL",
                               "native_C_evaluations": len(cache),
                               "local_ratio_bracket": list(bracket)})
        if errors:
            print("F124_FIXEDJ_POINT_FAIL_RETAINED", json.dumps(errors[-1], sort_keys=True), flush=True)

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
    status = "F124_LOWER_HALF_BISECTION_COMPLETE" if len(solutions)==1 and not errors else "FAIL_CLOSED"
    out = {
        "schema": "J0740_F124_NATIVE_C_LOWER_HALF_BISECTION_V1",
        "status": status, "diagnostic_only": True, "mesh": GRID,
        "EOS_sha256": EOS_SHA, "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL,
        "diagnostic_root_tolerance": DIAGNOSTIC_ROOT_TOLERANCE,
        "pinned_RNS_upstream_commit": RNS_COMMIT,
        "input_F123_artifact_sha256": F123_ZIP_SHA,
        "input_F123_status": f123_result["status"],
        "input_F122_artifact_sha256": F122_ZIP_SHA,
        "density_points_g_cm3": [LOW_RHO, MID_RHO, HIGH_RHO],
        "native_C_call_count": len(cache),
        "native_C_attempt_count": len(cache)+len(rejected_trials),
        "native_C_rejected_trials": rejected_trials,
        "trial_rows": list(cache.values()),
        "fixed_J_solutions": solutions, "mass_steps": mass_steps,
        "native_C_errors": errors, "raw_journal_sha256": sha(journal.read_bytes()),
        "interpretation": (
            "One midpoint bisects F123's remaining lower-half sampled mass step on the same mesh. "
            "This localizes the sampled feature only; it does not establish physical cause, branch "
            "identity, formal mesh convergence, a physical maximum, rotating-star stability, or "
            "photon-native EOS evidence."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print("F124_RESULT", json.dumps({k:out[k] for k in (
        "status","native_C_call_count","fixed_J_solutions","mass_steps","native_C_errors")},sort_keys=True),flush=True)
    if status != "F124_LOWER_HALF_BISECTION_COMPLETE":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
