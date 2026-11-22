#!/usr/bin/env python3
"""F108: dense, fixed-J RNS C scan around the F107 local mass dip.

This is a diagnostic density scan. Passing means every planned native-C
fixed-J point and provenance check passed; it does not certify a unique peak.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

F107_ZIP_SHA = "9e71a4332f6de293cab3c7af8f41f1b6b79ae55ae28df16bd4a877ebfec75b7f"
F107_RESULT = "F107/F107_DENSE_LOCAL_501x1001.json"
F107_JOURNAL = "F107/F107_DENSE_LOCAL_501x1001.jsonl"
F107_INNER_F106 = "F106/F106_artifact.zip"
F106_ZIP_SHA = "c114b73fda17a4822cb656b624fc41babee85785e476a5e09edf38ae5680a407"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
GRID = "501x1001"
# 2.615--2.645 in 0.001e15 steps. Reuse already accepted 2.620, 2.630,
# and 2.640 points; never call native C twice at an existing density.
SCAN_TICKS = tuple(range(2615, 2646))
REUSE_TICKS = {2620, 2630, 2640}
RHO = np.asarray([tick * 1e12 for tick in SCAN_TICKS if tick not in REUSE_TICKS])


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_f107(path: Path) -> tuple[dict, list[dict], dict]:
    raw = path.read_bytes()
    if sha(raw) != F107_ZIP_SHA:
        raise ValueError("F107_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F107_ARTIFACT_ZIP_CRC_FAILURE")
        result = json.loads(archive.read(F107_RESULT))
        journal_bytes = archive.read(F107_JOURNAL)
        f106_bytes = archive.read(F107_INNER_F106)
    if sha(journal_bytes) != result.get("journal_sha256"):
        raise ValueError("F107_RAW_JOURNAL_SHA256_MISMATCH")
    if sha(f106_bytes) != F106_ZIP_SHA:
        raise ValueError("F106_NESTED_ARTIFACT_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines()]
    if (result.get("status") != "DENSE_LOCAL_SCAN_PASS"
            or result.get("mesh") != GRID
            or result.get("EOS_sha256") != EOS_SHA
            or result.get("target_J_cgs") != f106.TARGET_J
            or result.get("J_relative_tolerance") != f106.J_REL_TOL
            or result.get("new_density_points_count") != 14
            or result.get("new_native_C_call_count") != 138
            or len(result.get("new_native_C_stars", [])) != 14
            or len(rows) != 138
            or result.get("native_C_errors")):
        raise ValueError("F107_PRIOR_EVIDENCE_NOT_ACCEPTED")
    if any(r.get("mesh") != GRID or not r.get("real_native_RNS_C") for r in rows):
        raise ValueError("F107_RAW_ROW_NOT_NATIVE_C_OR_GRID_MISMATCH")
    for star in result["new_native_C_stars"]:
        group = [r for r in rows if r.get("index") == star.get("index")]
        if len(group) != star.get("native_C_evaluations"):
            raise ValueError("F107_PER_STAR_C_COUNT_MISMATCH")
        if not any(math.isclose(r["r_ratio"], star["r_ratio"], rel_tol=0, abs_tol=1e-12)
                   and math.isclose(r["M_msun"], star["M_msun"], rel_tol=0, abs_tol=1e-12)
                   and r["J_relative_error"] <= f106.J_REL_TOL for r in group):
            raise ValueError("F107_FINAL_ROOT_NOT_IN_C_JOURNAL")
    # The prior workflow's combined array is checked against the validated
    # F106/F107 rows, then used only as already measured density points.
    combined = result.get("combined_local_samples_with_F106_reference", [])
    if len(combined) != 21 or len({round(r["rho_g_cm3"]) for r in combined}) != 21:
        raise ValueError("F107_COMBINED_REFERENCE_SAMPLE_SET_INVALID")
    return result, rows, {str(k): v for k, v in enumerate(combined)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f107", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()

    prior, _, _ = read_f107(a.f107)
    if sha(a.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not a.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")
    eos = np.loadtxt(a.eos, skiprows=1)
    if eos.shape != (1981, 4) or not np.all(np.diff(eos[:, 0]) > 0):
        raise ValueError("PINNED_F99_EOS_TABLE_SHAPE_OR_MONOTONICITY_FAIL")
    journal = a.out.with_suffix(".jsonl")
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F108_RAW_NATIVE_C_JOURNAL")

    new_rows, errors = [], []
    for i, rho in enumerate(RHO):
        try:
            row = f106.solve_one(a.rns, a.eos, float(rho), journal, i)
            node = int(np.searchsorted(eos[:, 0], float(rho), side="right"))
            row["eos_interval_left_node_index_zero_based"] = max(0, node - 1)
            row["eos_interval_right_node_index_zero_based"] = min(len(eos) - 1, node)
            row["nearest_eos_density_node_delta_g_cm3"] = float(
                eos[np.argmin(np.abs(eos[:, 0] - rho)), 0] - rho)
            new_rows.append(row)
            print("F108_NATIVE_C_FIXED_J_PASS", i, row["rho_g_cm3"],
                  row["M_msun"], row["J_relative_error"],
                  row["native_C_evaluations"], flush=True)
        except Exception as exc:
            errors.append({"index": i, "rho_g_cm3": float(rho), "error": repr(exc)})
            print("F108_NATIVE_C_POINT_FAIL_RETAINED", i, repr(exc), flush=True)

    existing = prior["combined_local_samples_with_F106_reference"]
    by_tick = {int(round(r["rho_g_cm3"] / 1e12)): dict(r) for r in existing}
    reused_ticks = []
    for tick in SCAN_TICKS:
        if tick in REUSE_TICKS:
            if tick not in by_tick:
                raise ValueError("EXPECTED_PRIOR_DENSITY_NOT_FOUND")
            reused_ticks.append(tick)
    for row in new_rows:
        tick = int(round(row["rho_g_cm3"] / 1e12))
        if tick in by_tick or tick in REUSE_TICKS:
            raise ValueError("DUPLICATE_DENSITY_RECORD")
        by_tick[tick] = row
    focus = [by_tick[t] for t in sorted(by_tick) if SCAN_TICKS[0] <= t <= SCAN_TICKS[-1]]
    focus.sort(key=lambda row: row["rho_g_cm3"])
    slopes = np.diff([r["M_msun"] for r in focus]) / np.diff(
        np.asarray([r["rho_g_cm3"] for r in focus]) / 1e15)
    sign_changes = [i for i in range(len(slopes) - 1)
                    if slopes[i] * slopes[i + 1] < 0]
    # The scan status concerns execution and provenance only.
    status = ("F108_NATIVE_C_FINE_SCAN_PASS"
              if len(new_rows) == len(RHO) and not errors and len(focus) == len(SCAN_TICKS)
              else "FAIL_CLOSED")
    out = {
        "schema": "J0740_F108_NATIVE_C_501x1001_FINE_FIXED_J_DENSITY_DIAGNOSTIC_V1",
        "status": status,
        "diagnostic_only": True,
        "mesh": GRID,
        "EOS_sha256": EOS_SHA,
        "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL,
        "pinned_RNS_upstream_commit": "97e85d325a33e37f702306414533f6cd77812477",
        "input_F107_artifact_sha256": F107_ZIP_SHA,
        "input_F107_status": prior["status"],
        "EOS_table_first_column": "energy density divided by c^2 (g/cm^3)",
        "EOS_table_interval_node_indices_zero_based": [1968, 1969],
        "scan_density_g_cm3": [float(rho) for rho in RHO],
        "reused_accepted_density_ticks_1e12_g_cm3": reused_ticks,
        "new_native_C_point_count": len(new_rows),
        "new_native_C_call_count": sum(r["native_C_evaluations"] for r in new_rows),
        "new_native_C_stars": new_rows,
        "native_C_errors": errors,
        "focus_samples_including_prior_points": focus,
        "mass_slopes_Msun_per_1e15_g_cm3": slopes.tolist(),
        "mass_slope_sign_change_count": len(sign_changes),
        "mass_slope_sign_change_intervals": [
            {"left_density_1e15": focus[i]["rho_g_cm3"] / 1e15,
             "middle_density_1e15": focus[i + 1]["rho_g_cm3"] / 1e15,
             "right_density_1e15": focus[i + 2]["rho_g_cm3"] / 1e15,
             "left_slope": float(slopes[i]), "right_slope": float(slopes[i + 1])}
            for i in sign_changes],
        "sampled_maximum_in_focus_window": max(focus, key=lambda r: r["M_msun"]),
        "journal_sha256": sha(journal.read_bytes()) if journal.exists() else None,
        "interpretation": "Diagnostic only. A pass proves that planned native-C roots and provenance checks passed; it does not certify a unique physical maximum, branch identity, continuum/grid convergence, dynamical stability, or photon-native EOS evidence.",
        "branch_or_interpolation_cause": "UNRESOLVED_BY_THIS_SCAN",
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n",
                     encoding="utf-8")
    print("F108_RESULT", json.dumps({k: out[k] for k in (
        "status", "new_native_C_point_count", "new_native_C_call_count",
        "mass_slope_sign_change_count", "mass_slope_sign_change_intervals",
        "sampled_maximum_in_focus_window", "branch_or_interpolation_cause")},
        sort_keys=True), flush=True)
    if status != "F108_NATIVE_C_FINE_SCAN_PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
