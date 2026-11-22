#!/usr/bin/env python3
"""F112 compares the F111 localized mass step on a finer native RNS C mesh."""
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

F111_ZIP_SHA = "55dea39f39070c891a67d776656ead97888641f048892befb3b3080e134bf29f"
F110_ZIP_SHA = "30fcc9f4c12b1575ee71fb066eb3bc8da1b0c596d9aa902e90018ea3618ac912"
F111_RESULT = "F111/F111_FIXED_RATIO_JUMP_BRACKET.json"
F111_JOURNAL = "F111/F111_FIXED_RATIO_JUMP_BRACKET.jsonl"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
HIGH_GRID = "1001x2001"
LOW_GRID = "501x1001"
BRACKET_TICKS_1E10 = (262228, 262229)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_f111(path: Path):
    raw = path.read_bytes()
    if sha(raw) != F111_ZIP_SHA:
        raise ValueError("F111_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F111_ARTIFACT_ZIP_CRC_FAILURE")
        result = json.loads(archive.read(F111_RESULT))
        journal_bytes = archive.read(F111_JOURNAL)
        f110_bytes = archive.read("F110/F110_artifact.zip")
    if sha(f110_bytes) != F110_ZIP_SHA:
        raise ValueError("F111_NESTED_F110_BASELINE_SHA256_MISMATCH")
    if sha(journal_bytes) != result.get("raw_journal_sha256"):
        raise ValueError("F111_RAW_JOURNAL_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines()]
    if (result.get("status") != "F111_FIXED_RATIO_JUMP_BRACKET_COMPLETE"
            or result.get("diagnostic_only") is not True
            or result.get("mesh") != LOW_GRID
            or result.get("EOS_sha256") != EOS_SHA
            or result.get("pinned_RNS_upstream_commit") != RNS_COMMIT
            or result.get("input_F110_artifact_sha256") != F110_ZIP_SHA
            or result.get("new_native_C_point_count") != 18
            or result.get("new_native_C_call_count") != 18
            or result.get("native_C_errors")
            or len(rows) != 18):
        raise ValueError("F111_BASELINE_NOT_ACCEPTED")
    if any(r.get("mesh") != LOW_GRID or not r.get("real_native_RNS_C") for r in rows):
        raise ValueError("F111_RAW_ROW_NOT_NATIVE_C_OR_GRID_MISMATCH")
    return result, rows

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f111", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    baseline, _ = read_f111(args.f111)
    if sha(args.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not args.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")
    ratios = baseline["fixed_axis_ratios"]
    low = {}
    for label in ("A", "B"):
        points = baseline["series_by_fixed_ratio"][label]["points"]
        selected = [p for p in points
                    if int(round(p["rho_g_cm3"] / 1e10)) in BRACKET_TICKS_1E10]
        if len(selected) != 2:
            raise ValueError("F111_GRID_COMPARISON_ENDPOINTS_MISSING")
        low[label] = {int(round(p["rho_g_cm3"] / 1e10)): p for p in selected}
    journal = args.out.with_suffix(".jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F112_RAW_HIGH_GRID_JOURNAL")
    high = {"A": [], "B": []}
    errors = []
    with journal.open("x", encoding="utf-8") as stream:
        for label in ("A", "B"):
            for tick in BRACKET_TICKS_1E10:
                rho = tick * 1e10
                index = len(high["A"]) + len(high["B"]) + len(errors)
                try:
                    star = f106.call_rns(args.rns, args.eos, rho, ratios[label])
                    signed = star["J_cgs"] / f106.TARGET_J - 1.0
                    row = {
                        "index": index, "rho_tick_1e10_g_cm3": tick,
                        "rho_g_cm3": rho, "ratio_label": label,
                        "r_ratio": ratios[label], "M_msun": star["M_msun"],
                        "R_eq_km": star["R_equatorial_km"], "f_hz": star["spin_hz"],
                        "J_cgs": star["J_cgs"], "J_signed_relative_error": signed,
                        "J_relative_error": abs(signed),
                        "within_target_tolerance": abs(signed) <= f106.J_REL_TOL,
                        "mesh": HIGH_GRID, "real_native_RNS_C": True,
                    }
                    stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                    stream.flush()
                    high[label].append(row)
                    print("F112_HIGH_GRID_NATIVE_C", json.dumps(row, sort_keys=True), flush=True)
                except Exception as exc:
                    error = {"index": index, "rho_g_cm3": rho, "ratio_label": label,
                             "r_ratio": ratios[label], "error": repr(exc)}
                    errors.append(error)
                    print("F112_NATIVE_C_POINT_FAIL_RETAINED",
                          json.dumps(error, sort_keys=True), flush=True)
    comparisons = {}
    for label in ("A", "B"):
        high_by_tick = {row["rho_tick_1e10_g_cm3"]: row for row in high[label]}
        comparisons[label] = []
        for tick in BRACKET_TICKS_1E10:
            if tick in high_by_tick:
                h = high_by_tick[tick]
                l = low[label][tick]
                comparisons[label].append({
                    "rho_g_cm3": h["rho_g_cm3"], "r_ratio": ratios[label],
                    "low_grid_M_msun": l["M_msun"], "high_grid_M_msun": h["M_msun"],
                    "high_minus_low_M_msun": h["M_msun"] - l["M_msun"],
                    "low_grid_R_eq_km": l["R_eq_km"], "high_grid_R_eq_km": h["R_eq_km"],
                    "high_minus_low_R_eq_km": h["R_eq_km"] - l["R_eq_km"],
                    "high_grid_J_signed_relative_error": h["J_signed_relative_error"],
                })
        if len(comparisons[label]) == 2:
            comparisons[label].append({
                "derived": "density_step",
                "low_grid_delta_M_msun": (
                    low[label][BRACKET_TICKS_1E10[1]]["M_msun"]
                    - low[label][BRACKET_TICKS_1E10[0]]["M_msun"]),
                "high_grid_delta_M_msun": (
                    high_by_tick[BRACKET_TICKS_1E10[1]]["M_msun"]
                    - high_by_tick[BRACKET_TICKS_1E10[0]]["M_msun"]),
            })
    status = "F112_HIGH_GRID_CROSSCHECK_COMPLETE" if len(journal.read_text().splitlines()) == 4 and not errors else "FAIL_CLOSED"
    out = {
        "schema": "J0740_F112_NATIVE_C_HIGH_GRID_MASS_STEP_CROSSCHECK_V1",
        "status": status, "diagnostic_only": True,
        "low_grid": LOW_GRID, "high_grid": HIGH_GRID,
        "EOS_sha256": EOS_SHA, "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL, "pinned_RNS_upstream_commit": RNS_COMMIT,
        "input_F111_artifact_sha256": F111_ZIP_SHA,
        "input_F111_status": baseline["status"],
        "fixed_axis_ratios": ratios, "bracket_density_ticks_1e10_g_cm3": list(BRACKET_TICKS_1E10),
        "new_native_C_point_count": sum(len(v) for v in high.values()),
        "new_native_C_call_count": sum(len(v) for v in high.values()),
        "high_grid_native_C_rows": high, "low_vs_high_grid_comparison": comparisons,
        "native_C_errors": errors, "raw_journal_sha256": sha(journal.read_bytes()),
        "interpretation": (
            "This compares fixed-ratio outputs on two spatial meshes at two densities. "
            "It is not a fixed-J continuum-convergence proof and cannot establish "
            "a physical EOS discontinuity, branch identity, physical maximum, "
            "dynamical stability, or photon-native EOS evidence."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8")
    print("F112_RESULT", json.dumps({
        "status": status, "call_count": out["new_native_C_call_count"],
        "grid_delta_mass": {
            label: comparisons.get(label, [])[-1] if comparisons.get(label) else None
            for label in ("A", "B")
        },
        "native_C_errors": errors,
    }, sort_keys=True), flush=True)
    if status != "F112_HIGH_GRID_CROSSCHECK_COMPLETE":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
