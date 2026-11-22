#!/usr/bin/env python3
"""F118 resolves three fixed-J points inside the localized F99 density interval."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from scipy.optimize import brentq

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

F117_ZIP_SHA = "ab681b37c5c863e80b0666a4cb8801a03d3b887b920abb0324ec24f0a7044719"
F116_ZIP_SHA = "2947996a32d1db249830faa6014f7a75ebfd913c1edde98acaad074742d91f7d"
F117_RESULT = "F117/F117_NEIGHBOR_DENSITY_FIXEDJ_ROOTS.json"
F117_JOURNAL = "F117/F117_NEIGHBOR_DENSITY_FIXEDJ_ROOTS.jsonl"
F116_RESULT = "F116/F116_FIFTH_GRID_FIXEDJ_ROOTS.json"
F116_JOURNAL = "F116/F116_FIFTH_GRID_FIXEDJ_ROOTS.jsonl"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
GRID = "2501x5001"
RHO_TICKS_1E9 = (2622282, 2622285, 2622288)
RHO_SCALE = 1e9
RATIO_BRACKET_HALF_WIDTH = 2.5e-5

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_f117(path: Path):
    raw = path.read_bytes()
    if sha(raw) != F117_ZIP_SHA:
        raise ValueError("F117_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F117_ARTIFACT_ZIP_CRC_FAILURE")
        result = json.loads(archive.read(F117_RESULT))
        journal_bytes = archive.read(F117_JOURNAL)
        f116_bytes = archive.read("F116/F116_artifact.zip")
    if sha(f116_bytes) != F116_ZIP_SHA:
        raise ValueError("F117_NESTED_F116_BASELINE_SHA256_MISMATCH")
    if sha(journal_bytes) != result.get("raw_journal_sha256"):
        raise ValueError("F117_RAW_JOURNAL_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines()]
    if (result.get("status") != "F117_NEIGHBOR_DENSITY_FIXEDJ_ROOTS_COMPLETE"
            or result.get("diagnostic_only") is not True
            or result.get("mesh") != GRID
            or result.get("EOS_sha256") != EOS_SHA
            or result.get("target_J_cgs") != f106.TARGET_J
            or result.get("J_relative_tolerance") != f106.J_REL_TOL
            or result.get("pinned_RNS_upstream_commit") != RNS_COMMIT
            or result.get("input_F116_artifact_sha256") != F116_ZIP_SHA
            or result.get("new_native_C_call_count") != 10
            or len(rows) != 10
            or len(result.get("fixed_J_solutions", [])) != 2
            or result.get("native_C_errors")):
        raise ValueError("F117_BASELINE_NOT_ACCEPTED")
    if any(row.get("mesh") != GRID or not row.get("real_native_RNS_C") for row in rows):
        raise ValueError("F117_RAW_ROW_INVALID")
    with zipfile.ZipFile(BytesIO(f116_bytes)) as archive:
        if archive.testzip() is not None:
            raise ValueError("NESTED_F116_ARTIFACT_CRC_FAILURE")
        f116_result = json.loads(archive.read(F116_RESULT))
        f116_journal = archive.read(F116_JOURNAL)
    if (sha(f116_journal) != f116_result.get("raw_journal_sha256")
            or f116_result.get("status") != "F116_FIFTH_GRID_FIXEDJ_ROOTS_COMPLETE"
            or f116_result.get("mesh") != GRID
            or f116_result.get("new_native_C_call_count") != 10
            or f116_result.get("native_C_errors")
            or [x.get("rho_tick_1e10_g_cm3") for x in f116_result.get("fixed_J_solutions", [])] != [262228, 262229]):
        raise ValueError("F116_INNER_ROOT_BASELINE_NOT_ACCEPTED")
    return result, rows, f116_result

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f117", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    outer_baseline, _, inner_baseline = read_f117(args.f117)
    if sha(args.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not args.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")
    inner = sorted(inner_baseline["fixed_J_solutions"], key=lambda row: row["rho_g_cm3"])
    low_root, high_root = inner
    def baseline_linear(field: str, rho: float) -> float:
        return low_root[field] + (rho-low_root["rho_g_cm3"]) * (
            high_root[field]-low_root[field]) / (
            high_root["rho_g_cm3"]-low_root["rho_g_cm3"])
    journal = args.out.with_suffix(".jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F118_RAW_FIXEDJ_JOURNAL")
    all_rows, solutions, errors = [], [], []
    with journal.open("x", encoding="utf-8") as stream:
        for rho_tick in RHO_TICKS_1E9:
            rho = rho_tick * RHO_SCALE
            center = baseline_linear("selected_r_ratio", rho)
            bracket = (center-RATIO_BRACKET_HALF_WIDTH, center+RATIO_BRACKET_HALF_WIDTH)
            cache: dict[str, dict] = {}
            def evaluate(ratio: float) -> float:
                ratio_input = float(f"{ratio:.12f}")
                key = f"{ratio_input:.12f}"
                if key not in cache:
                    star = f106.call_rns(args.rns, args.eos, rho, ratio_input)
                    signed = star["J_cgs"] / f106.TARGET_J - 1.0
                    row = {
                        "index": len(all_rows), "rho_tick_1e9_g_cm3": rho_tick,
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
                    print("F118_NATIVE_C_FIXEDJ_TRIAL", json.dumps(row, sort_keys=True), flush=True)
                return cache[key]["J_signed_relative_error"]
            try:
                low, high = sorted(bracket)
                f_low, f_high = evaluate(low), evaluate(high)
                if abs(f_low) <= f106.J_REL_TOL or abs(f_high) <= f106.J_REL_TOL:
                    pass
                elif f_low * f_high < 0:
                    root = brentq(evaluate, low, high, xtol=1e-10, rtol=5e-13, maxiter=60)
                    evaluate(root)
                else:
                    raise RuntimeError("F118_INTRADENSITY_J_BRACKET_NOT_FOUND")
                accepted = min(cache.values(), key=lambda row: row["J_relative_error"])
                if accepted["J_relative_error"] > f106.J_REL_TOL:
                    raise RuntimeError("F118_INTRADENSITY_J_TOLERANCE_FAIL")
                solutions.append({
                    "rho_tick_1e9_g_cm3": rho_tick, "rho_g_cm3": rho,
                    "selected_r_ratio": accepted["r_ratio_C_input"],
                    "M_msun": accepted["M_msun"], "R_eq_km": accepted["R_eq_km"],
                    "f_hz": accepted["f_hz"], "J_cgs": accepted["J_cgs"],
                    "J_relative_error": accepted["J_relative_error"],
                    "native_C_evaluations": len(cache), "real_native_RNS_C": True,
                    "mesh": GRID, "baseline_linear_r_ratio_center": center,
                    "baseline_linear_M_msun": baseline_linear("M_msun", rho),
                    "ratio_bracket_center_source": "linear interpolation between F116 inner fixed-J roots",
                    "local_ratio_bracket": [low, high],
                })
            except Exception as exc:
                errors.append({"rho_g_cm3": rho, "rho_tick_1e9_g_cm3": rho_tick,
                               "error": repr(exc), "native_C_evaluations": len(cache),
                               "local_ratio_bracket": list(bracket)})
                print("F118_FIXEDJ_POINT_FAIL_RETAINED", json.dumps(errors[-1], sort_keys=True), flush=True)
    solutions.sort(key=lambda row: row["rho_g_cm3"])
    mass_steps = []
    if len(solutions) == 3:
        points = [{"rho_g_cm3": low_root["rho_g_cm3"], "M_msun": low_root["M_msun"], "source": "F116 baseline"},
                  *[{"rho_g_cm3": row["rho_g_cm3"], "M_msun": row["M_msun"], "source": "F118 native C"} for row in solutions],
                  {"rho_g_cm3": high_root["rho_g_cm3"], "M_msun": high_root["M_msun"], "source": "F116 baseline"}]
        for a, b in zip(points, points[1:]):
            drho = b["rho_g_cm3"] - a["rho_g_cm3"]
            dm = b["M_msun"] - a["M_msun"]
            mass_steps.append({"rho_low_g_cm3": a["rho_g_cm3"], "rho_high_g_cm3": b["rho_g_cm3"],
                               "mass_delta_msun": dm, "density_delta_g_cm3": drho,
                               "mass_delta_per_1e9_g_cm3_msun": dm/(drho/RHO_SCALE),
                               "lower_source": a["source"], "upper_source": b["source"]})
    status = "F118_INTRADENSITY_FIXEDJ_SCAN_COMPLETE" if len(solutions) == 3 and not errors else "FAIL_CLOSED"
    out = {
        "schema": "J0740_F118_NATIVE_C_INTRADENSITY_FIXEDJ_SCAN_V1",
        "status": status, "diagnostic_only": True, "mesh": GRID,
        "EOS_sha256": EOS_SHA, "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL, "pinned_RNS_upstream_commit": RNS_COMMIT,
        "input_F117_artifact_sha256": F117_ZIP_SHA, "input_F117_status": outer_baseline["status"],
        "input_F116_artifact_sha256": F116_ZIP_SHA, "input_F116_status": inner_baseline["status"],
        "density_ticks_1e9_g_cm3": list(RHO_TICKS_1E9),
        "native_C_call_count": len(all_rows), "trial_rows": all_rows,
        "fixed_J_solutions": solutions, "mass_steps": mass_steps,
        "inner_bracket_mass_delta_msun": high_root["M_msun"]-low_root["M_msun"],
        "native_C_errors": errors, "raw_journal_sha256": sha(journal.read_bytes()),
        "interpretation": (
            "Three interior fixed-J samples can localize the mass increase within the interval; "
            "they do not establish its physical cause, branch identity, mesh convergence, "
            "a physical maximum, rotating-star stability, or photon-native EOS evidence."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print("F118_RESULT", json.dumps({"status": status, "native_C_call_count": len(all_rows),
          "fixed_J_solutions": solutions, "mass_steps": mass_steps, "native_C_errors": errors}, sort_keys=True), flush=True)
    if status != "F118_INTRADENSITY_FIXEDJ_SCAN_COMPLETE":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
