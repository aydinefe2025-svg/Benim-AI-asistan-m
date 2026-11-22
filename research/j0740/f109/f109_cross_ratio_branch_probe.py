#!/usr/bin/env python3
"""F109 cross-evaluates adjacent F108 fixed-J ratios with native RNS C."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

F108_ZIP_SHA = "281f2521f68f40f94da250a385bafb4d84ace2b6ebed8b466c0937d8f72d3eb5"
F108_RESULT = "F108/F108_FINE_DENSITY_501x1001.json"
F108_JOURNAL = "F108/F108_FINE_DENSITY_501x1001.jsonl"
F108_F107 = "F107/F107_artifact.zip"
F108_F107_SHA = "9e71a4332f6de293cab3c7af8f41f1b6b79ae55ae28df16bd4a877ebfec75b7f"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
GRID = "501x1001"
CROSS_DENSITY_TICKS = (2622, 2623)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_f108(path: Path) -> tuple[dict, list[dict], dict[int, dict]]:
    raw = path.read_bytes()
    if sha(raw) != F108_ZIP_SHA:
        raise ValueError("F108_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F108_ARTIFACT_ZIP_CRC_FAILURE")
        result = json.loads(archive.read(F108_RESULT))
        journal_bytes = archive.read(F108_JOURNAL)
        f107_bytes = archive.read(F108_F107)
    if sha(journal_bytes) != result.get("journal_sha256"):
        raise ValueError("F108_RAW_JOURNAL_SHA256_MISMATCH")
    if sha(f107_bytes) != F108_F107_SHA:
        raise ValueError("F108_F107_BASELINE_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines()]
    if (result.get("status") != "F108_NATIVE_C_FINE_SCAN_PASS"
            or result.get("diagnostic_only") is not True
            or result.get("mesh") != GRID
            or result.get("EOS_sha256") != EOS_SHA
            or result.get("target_J_cgs") != f106.TARGET_J
            or result.get("J_relative_tolerance") != f106.J_REL_TOL
            or result.get("pinned_RNS_upstream_commit") != RNS_COMMIT
            or result.get("new_native_C_point_count") != 28
            or result.get("new_native_C_call_count") != 280
            or len(result.get("new_native_C_stars", [])) != 28
            or len(rows) != 280
            or result.get("native_C_errors")):
        raise ValueError("F108_BASELINE_NOT_ACCEPTED")
    if any(row.get("mesh") != GRID or not row.get("real_native_RNS_C") for row in rows):
        raise ValueError("F108_RAW_ROW_NOT_NATIVE_C_OR_GRID_MISMATCH")
    by_tick: dict[int, dict] = {}
    for star in result["new_native_C_stars"]:
        tick = int(round(star["rho_g_cm3"] / 1e12))
        if tick in by_tick:
            raise ValueError("DUPLICATE_F108_DENSITY")
        group = [row for row in rows if row.get("index") == star.get("index")]
        if len(group) != star.get("native_C_evaluations"):
            raise ValueError("F108_PER_STAR_CALL_COUNT_MISMATCH")
        if not any(
            math.isclose(row["r_ratio"], star["r_ratio"], rel_tol=0, abs_tol=1e-12)
            and math.isclose(row["M_msun"], star["M_msun"], rel_tol=0, abs_tol=1e-12)
            and row["J_relative_error"] <= f106.J_REL_TOL
            for row in group
        ):
            raise ValueError("F108_SELECTED_ROOT_NOT_IN_RAW_C_JOURNAL")
        by_tick[tick] = star
    if any(tick not in by_tick for tick in CROSS_DENSITY_TICKS):
        raise ValueError("F108_CROSS_DENSITIES_MISSING")
    return result, rows, by_tick

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f108", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    prior, _, stars = read_f108(args.f108)
    if sha(args.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not args.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")
    a, b = stars[2622], stars[2623]
    cases = [
        {"case": "density_2622_with_ratio_selected_at_2623",
         "rho_g_cm3": a["rho_g_cm3"], "ratio_source_density_g_cm3": b["rho_g_cm3"],
         "r_ratio": float(f"{b['r_ratio']:.12f}")},
        {"case": "density_2623_with_ratio_selected_at_2622",
         "rho_g_cm3": b["rho_g_cm3"], "ratio_source_density_g_cm3": a["rho_g_cm3"],
         "r_ratio": float(f"{a['r_ratio']:.12f}")},
    ]
    journal = args.out.with_suffix(".jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F109_RAW_CROSS_PROBE_JOURNAL")
    results = []
    with journal.open("x", encoding="utf-8") as stream:
        for index, case in enumerate(cases):
            star = f106.call_rns(args.rns, args.eos, case["rho_g_cm3"], case["r_ratio"])
            signed_error = star["J_cgs"] / f106.TARGET_J - 1.0
            row = {
                "index": index, "case": case["case"],
                "rho_g_cm3": case["rho_g_cm3"],
                "ratio_source_density_g_cm3": case["ratio_source_density_g_cm3"],
                "r_ratio_C_input": case["r_ratio"],
                "M_msun": star["M_msun"], "R_eq_km": star["R_equatorial_km"],
                "f_hz": star["spin_hz"], "J_cgs": star["J_cgs"],
                "J_signed_relative_error": signed_error,
                "J_relative_error": abs(signed_error),
                "within_target_tolerance": abs(signed_error) <= f106.J_REL_TOL,
                "mesh": GRID, "real_native_RNS_C": True,
            }
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            results.append(row)
            print("F109_NATIVE_C_CROSS_RATIO", json.dumps(row, sort_keys=True), flush=True)
    both = all(row["within_target_tolerance"] for row in results)
    neither = not any(row["within_target_tolerance"] for row in results)
    classification = ("BOTH_CROSS_RATIOS_WITHIN_TARGET_TOLERANCE" if both else
                      "NEITHER_CROSS_RATIO_WITHIN_TARGET_TOLERANCE" if neither else
                      "ONE_CROSS_RATIO_WITHIN_TARGET_TOLERANCE")
    out = {
        "schema": "J0740_F109_NATIVE_C_CROSS_RATIO_BRANCH_DIAGNOSTIC_V1",
        "status": "F109_CROSS_RATIO_NATIVE_C_COMPLETE", "diagnostic_only": True,
        "mesh": GRID, "EOS_sha256": EOS_SHA, "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL,
        "pinned_RNS_upstream_commit": RNS_COMMIT,
        "input_F108_artifact_sha256": F108_ZIP_SHA, "input_F108_status": prior["status"],
        "cross_probe_count": len(results), "new_native_C_call_count": len(results),
        "cross_probes": results, "classification": classification,
        "raw_journal_sha256": sha(journal.read_bytes()),
        "interpretation": (
            "Tests only whether the two neighboring selected ratios, transplanted "
            "across densities, meet the existing target-J tolerance. It cannot prove "
            "branch identity, a physical maximum, continuum/grid convergence, "
            "dynamical stability, or photon-native EOS evidence."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8")
    print("F109_RESULT", json.dumps({
        "status": out["status"], "classification": classification,
        "cross_probe_count": len(results),
        "relative_J_errors": [row["J_relative_error"] for row in results],
    }, sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
