#!/usr/bin/env python3
"""F111 narrows the F110 fixed-ratio mass step to a 1e10 g/cm^3 bracket."""
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

F110_ZIP_SHA = "30fcc9f4c12b1575ee71fb066eb3bc8da1b0c596d9aa902e90018ea3618ac912"
F108_ZIP_SHA = "281f2521f68f40f94da250a385bafb4d84ace2b6ebed8b466c0937d8f72d3eb5"
F109_ZIP_SHA = "b515752355e222288dbc09b394260f69f522d8e2306ba2d77f11823339ea3750"
F110_RESULT = "F110/F110_FIXED_RATIO_DENSITY_SCAN.json"
F110_JOURNAL = "F110/F110_FIXED_RATIO_DENSITY_SCAN.jsonl"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
GRID = "501x1001"
INTERIOR_RHO_TICKS_1E10 = tuple(range(262221, 262230))

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_f110(path: Path):
    raw = path.read_bytes()
    if sha(raw) != F110_ZIP_SHA:
        raise ValueError("F110_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F110_ARTIFACT_ZIP_CRC_FAILURE")
        result = json.loads(archive.read(F110_RESULT))
        journal_bytes = archive.read(F110_JOURNAL)
        f108_bytes = archive.read("F108/F108_artifact.zip")
        f109_bytes = archive.read("F109/F109_artifact.zip")
    if sha(f108_bytes) != F108_ZIP_SHA or sha(f109_bytes) != F109_ZIP_SHA:
        raise ValueError("F110_NESTED_BASELINE_SHA256_MISMATCH")
    if sha(journal_bytes) != result.get("raw_journal_sha256"):
        raise ValueError("F110_RAW_JOURNAL_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines()]
    if (result.get("status") != "F110_FIXED_RATIO_DENSITY_SCAN_COMPLETE"
            or result.get("diagnostic_only") is not True
            or result.get("mesh") != GRID
            or result.get("EOS_sha256") != EOS_SHA
            or result.get("target_J_cgs") != f106.TARGET_J
            or result.get("J_relative_tolerance") != f106.J_REL_TOL
            or result.get("pinned_RNS_upstream_commit") != RNS_COMMIT
            or result.get("input_F108_artifact_sha256") != F108_ZIP_SHA
            or result.get("input_F109_artifact_sha256") != F109_ZIP_SHA
            or result.get("new_native_C_point_count") != 18
            or result.get("new_native_C_call_count") != 18
            or result.get("native_C_errors")
            or len(rows) != 18):
        raise ValueError("F110_BASELINE_NOT_ACCEPTED")
    if any(row.get("mesh") != GRID or not row.get("real_native_RNS_C") for row in rows):
        raise ValueError("F110_RAW_ROW_NOT_NATIVE_C_OR_GRID_MISMATCH")
    return result, rows

def summarize(points: list[dict]) -> dict:
    points = sorted(points, key=lambda row: row["rho_g_cm3"])
    deltas = [points[i + 1]["M_msun"] - points[i]["M_msun"]
              for i in range(len(points) - 1)]
    signs = [1 if x > 0 else -1 if x < 0 else 0 for x in deltas]
    changes = sum(1 for i in range(len(signs)-1)
                  if signs[i] and signs[i+1] and signs[i] != signs[i+1])
    k = max(range(len(deltas)), key=lambda i: abs(deltas[i]))
    return {
        "points": points,
        "mass_increments_msun": deltas,
        "mass_increment_sign_change_count": changes,
        "largest_mass_increment": {
            "left_rho_g_cm3": points[k]["rho_g_cm3"],
            "right_rho_g_cm3": points[k+1]["rho_g_cm3"],
            "delta_msun": deltas[k],
        },
        "min_abs_other_increment_msun": min(
            (abs(x) for i, x in enumerate(deltas) if i != k), default=None),
        "max_abs_other_increment_msun": max(
            (abs(x) for i, x in enumerate(deltas) if i != k), default=None),
    }

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f110", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    baseline, base_rows = read_f110(args.f110)
    if sha(args.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not args.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")
    ratios = baseline["fixed_axis_ratios"]
    endpoints = {"A": [], "B": []}
    for label in ("A", "B"):
        selected = [p for p in baseline["series_by_fixed_ratio"][label]["points"]
                    if int(round(p["rho_g_cm3"] / 1e11)) in (26222, 26223)]
        if len(selected) != 2:
            raise ValueError("F110_JUMP_BRACKET_ENDPOINTS_MISSING")
        for point in selected:
            tick = int(round(point["rho_g_cm3"] / 1e10))
            endpoints[label].append({
                **point,
                "rho_tick_1e10_g_cm3": tick,
                "r_ratio": ratios[label],
                "source": "F110 previously measured endpoint, not rerun",
            })
    journal = args.out.with_suffix(".jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F111_RAW_DENSITY_JOURNAL")
    new_rows, errors = [], []
    with journal.open("x", encoding="utf-8") as stream:
        for label in ("A", "B"):
            ratio = ratios[label]
            for tick in INTERIOR_RHO_TICKS_1E10:
                rho = tick * 1e10
                index = len(new_rows) + len(errors)
                try:
                    star = f106.call_rns(args.rns, args.eos, rho, ratio)
                    signed = star["J_cgs"] / f106.TARGET_J - 1.0
                    row = {
                        "index": index, "rho_tick_1e10_g_cm3": tick,
                        "rho_g_cm3": rho, "ratio_label": label, "r_ratio": ratio,
                        "M_msun": star["M_msun"], "R_eq_km": star["R_equatorial_km"],
                        "f_hz": star["spin_hz"], "J_cgs": star["J_cgs"],
                        "J_signed_relative_error": signed,
                        "J_relative_error": abs(signed),
                        "within_target_tolerance": abs(signed) <= f106.J_REL_TOL,
                        "mesh": GRID, "real_native_RNS_C": True,
                        "source": "F111 new direct native-C fixed-ratio call",
                    }
                    stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                    stream.flush()
                    new_rows.append(row)
                    print("F111_FIXED_RATIO_NATIVE_C", json.dumps(row, sort_keys=True), flush=True)
                except Exception as exc:
                    error = {"index": index, "rho_g_cm3": rho,
                             "ratio_label": label, "r_ratio": ratio, "error": repr(exc)}
                    errors.append(error)
                    print("F111_NATIVE_C_POINT_FAIL_RETAINED",
                          json.dumps(error, sort_keys=True), flush=True)
    combined = {"A": list(endpoints["A"]), "B": list(endpoints["B"])}
    for row in new_rows:
        combined[row["ratio_label"]].append(row)
    series = {label: summarize(points) for label, points in combined.items()}
    status = ("F111_FIXED_RATIO_JUMP_BRACKET_COMPLETE"
              if len(new_rows) == 18 and not errors else "FAIL_CLOSED")
    out = {
        "schema": "J0740_F111_NATIVE_C_FIXED_RATIO_JUMP_BRACKET_V1",
        "status": status, "diagnostic_only": True, "mesh": GRID,
        "EOS_sha256": EOS_SHA, "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL, "pinned_RNS_upstream_commit": RNS_COMMIT,
        "input_F110_artifact_sha256": F110_ZIP_SHA,
        "input_F110_status": baseline["status"],
        "fixed_axis_ratios": ratios,
        "interior_density_ticks_1e10_g_cm3": list(INTERIOR_RHO_TICKS_1E10),
        "reused_endpoint_count": 4, "new_native_C_point_count": len(new_rows),
        "new_native_C_call_count": len(new_rows), "native_C_errors": errors,
        "series_by_fixed_ratio": series,
        "raw_journal_sha256": sha(journal.read_bytes()),
        "interpretation": (
            "This scan only narrows the sampled fixed-ratio RNS C transition. "
            "The interior points are not fixed-J solutions and cannot establish "
            "a physical EOS discontinuity, branch identity, maximum, convergence, "
            "dynamical stability, or photon-native EOS evidence."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8")
    print("F111_RESULT", json.dumps({
        "status": status,
        "new_native_C_point_count": len(new_rows),
        "largest_mass_increments": {
            label: series[label]["largest_mass_increment"] for label in ("A", "B")
        },
        "native_C_errors": errors,
    }, sort_keys=True), flush=True)
    if status != "F111_FIXED_RATIO_JUMP_BRACKET_COMPLETE":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
