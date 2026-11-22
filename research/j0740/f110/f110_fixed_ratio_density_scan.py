#!/usr/bin/env python3
"""F110 measures density dependence of mass at two fixed RNS axis ratios."""
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
from research.j0740.f109 import f109_cross_ratio_branch_probe as f109

F108_ZIP_SHA = "281f2521f68f40f94da250a385bafb4d84ace2b6ebed8b466c0937d8f72d3eb5"
F109_ZIP_SHA = "b515752355e222288dbc09b394260f69f522d8e2306ba2d77f11823339ea3750"
F109_RESULT = "F109/F109_CROSS_RATIO_BRANCH_DIAGNOSTIC.json"
F109_JOURNAL = "F109/F109_CROSS_RATIO_BRANCH_DIAGNOSTIC.jsonl"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
GRID = "501x1001"
INTERIOR_RHO_TICKS_1E11 = tuple(range(26221, 26230))

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def load_baselines(f108_path: Path, f109_path: Path):
    if sha(f108_path.read_bytes()) != F108_ZIP_SHA:
        raise ValueError("F108_ARTIFACT_ZIP_SHA256_MISMATCH")
    result108, _, stars = f109.read_f108(f108_path)
    raw109 = f109_path.read_bytes()
    if sha(raw109) != F109_ZIP_SHA:
        raise ValueError("F109_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(f109_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("F109_ARTIFACT_ZIP_CRC_FAILURE")
        result109 = json.loads(archive.read(F109_RESULT))
        journal109 = archive.read(F109_JOURNAL)
    if sha(journal109) != result109.get("raw_journal_sha256"):
        raise ValueError("F109_RAW_JOURNAL_SHA256_MISMATCH")
    rows109 = [json.loads(line) for line in journal109.decode("utf-8").splitlines()]
    if (result109.get("status") != "F109_CROSS_RATIO_NATIVE_C_COMPLETE"
            or result109.get("diagnostic_only") is not True
            or result109.get("mesh") != GRID
            or result109.get("EOS_sha256") != EOS_SHA
            or result109.get("pinned_RNS_upstream_commit") != RNS_COMMIT
            or result109.get("input_F108_artifact_sha256") != F108_ZIP_SHA
            or result109.get("cross_probe_count") != 2
            or result109.get("new_native_C_call_count") != 2
            or len(rows109) != 2):
        raise ValueError("F109_BASELINE_NOT_ACCEPTED")
    if any(not row.get("real_native_RNS_C") or row.get("mesh") != GRID for row in rows109):
        raise ValueError("F109_RAW_ROW_NOT_NATIVE_C_OR_GRID_MISMATCH")
    stars_a, stars_b = stars[2622], stars[2623]
    ratio_a = float(f"{stars_a['r_ratio']:.12f}")
    ratio_b = float(f"{stars_b['r_ratio']:.12f}")
    by_case = {row["case"]: row for row in rows109}
    case_a = by_case.get("density_2622_with_ratio_selected_at_2623")
    case_b = by_case.get("density_2623_with_ratio_selected_at_2622")
    if case_a is None or case_b is None:
        raise ValueError("F109_CROSS_CASES_MISSING")
    if (not math.isclose(case_a["r_ratio_C_input"], ratio_b, abs_tol=1e-12)
            or not math.isclose(case_b["r_ratio_C_input"], ratio_a, abs_tol=1e-12)):
        raise ValueError("F109_CROSS_RATIO_MAPPING_MISMATCH")
    endpoints = {"A": [], "B": []}
    def from_star(label, tick, star):
        signed = star["J_cgs"] / f106.TARGET_J - 1.0
        endpoints[label].append({
            "rho_tick_1e11_g_cm3": tick, "rho_g_cm3": star["rho_g_cm3"],
            "ratio_label": label, "r_ratio": float(f"{star['r_ratio']:.12f}"),
            "M_msun": star["M_msun"], "R_eq_km": star["R_eq_km"],
            "f_hz": star["f_hz"], "J_cgs": star["J_cgs"],
            "J_signed_relative_error": signed, "J_relative_error": abs(signed),
            "real_native_RNS_C": True, "source": "F108 accepted fixed-J root",
        })
    from_star("A", 26220, stars_a)
    from_star("B", 26230, stars_b)
    for label, row in (("B", case_a), ("A", case_b)):
        tick = int(round(row["rho_g_cm3"] / 1e11))
        endpoints[label].append({
            "rho_tick_1e11_g_cm3": tick, "rho_g_cm3": row["rho_g_cm3"],
            "ratio_label": label, "r_ratio": row["r_ratio_C_input"],
            "M_msun": row["M_msun"], "R_eq_km": row["R_eq_km"],
            "f_hz": row["f_hz"], "J_cgs": row["J_cgs"],
            "J_signed_relative_error": row["J_signed_relative_error"],
            "J_relative_error": row["J_relative_error"],
            "real_native_RNS_C": True, "source": "F109 native-C cross-ratio result",
        })
    for label, records in endpoints.items():
        if len(records) != 2 or len({r["rho_tick_1e11_g_cm3"] for r in records}) != 2:
            raise ValueError("F108_F109_ENDPOINT_MATRIX_INCOMPLETE")
    return result108, result109, {"A": ratio_a, "B": ratio_b}, endpoints

def summarize_series(points: list[dict]) -> dict:
    points = sorted(points, key=lambda row: row["rho_g_cm3"])
    deltas = [points[i + 1]["M_msun"] - points[i]["M_msun"]
              for i in range(len(points) - 1)]
    signs = [1 if value > 0 else -1 if value < 0 else 0 for value in deltas]
    changes = sum(1 for i in range(len(signs) - 1)
                  if signs[i] and signs[i + 1] and signs[i] != signs[i + 1])
    return {
        "points": points,
        "mass_increments_msun": deltas,
        "mass_increment_sign_change_count": changes,
        "min_mass_increment_msun": min(deltas) if deltas else None,
        "max_mass_increment_msun": max(deltas) if deltas else None,
        "max_abs_mass_increment_msun": max((abs(x) for x in deltas), default=None),
    }

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f108", type=Path, required=True)
    ap.add_argument("--f109", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    base108, base109, ratios, endpoints = load_baselines(args.f108, args.f109)
    if sha(args.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    if not args.rns.is_file():
        raise FileNotFoundError("PINNED_NATIVE_RNS_BINARY_MISSING")
    journal = args.out.with_suffix(".jsonl")
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F110_RAW_DENSITY_JOURNAL")
    new_rows, errors = [], []
    with journal.open("x", encoding="utf-8") as stream:
        for label in ("A", "B"):
            ratio = ratios[label]
            for tick in INTERIOR_RHO_TICKS_1E11:
                rho = tick * 1e11
                index = len(new_rows) + len(errors)
                try:
                    star = f106.call_rns(args.rns, args.eos, rho, ratio)
                    signed = star["J_cgs"] / f106.TARGET_J - 1.0
                    row = {
                        "index": index, "rho_tick_1e11_g_cm3": tick,
                        "rho_g_cm3": rho, "ratio_label": label,
                        "r_ratio": ratio, "M_msun": star["M_msun"],
                        "R_eq_km": star["R_equatorial_km"], "f_hz": star["spin_hz"],
                        "J_cgs": star["J_cgs"], "J_signed_relative_error": signed,
                        "J_relative_error": abs(signed),
                        "within_target_tolerance": abs(signed) <= f106.J_REL_TOL,
                        "mesh": GRID, "real_native_RNS_C": True,
                    }
                    stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                    stream.flush()
                    new_rows.append(row)
                    print("F110_FIXED_RATIO_NATIVE_C", json.dumps(row, sort_keys=True), flush=True)
                except Exception as exc:
                    error = {"index": index, "rho_g_cm3": rho,
                             "ratio_label": label, "r_ratio": ratio, "error": repr(exc)}
                    errors.append(error)
                    print("F110_NATIVE_C_POINT_FAIL_RETAINED",
                          json.dumps(error, sort_keys=True), flush=True)
    combined = {"A": list(endpoints["A"]), "B": list(endpoints["B"])}
    for row in new_rows:
        combined[row["ratio_label"]].append(row)
    series = {label: summarize_series(rows) for label, rows in combined.items()}
    status = ("F110_FIXED_RATIO_DENSITY_SCAN_COMPLETE"
              if len(new_rows) == 18 and not errors else "FAIL_CLOSED")
    out = {
        "schema": "J0740_F110_NATIVE_C_FIXED_RATIO_DENSITY_SCAN_V1",
        "status": status, "diagnostic_only": True, "mesh": GRID,
        "EOS_sha256": EOS_SHA, "target_J_cgs": f106.TARGET_J,
        "J_relative_tolerance": f106.J_REL_TOL,
        "pinned_RNS_upstream_commit": RNS_COMMIT,
        "input_F108_artifact_sha256": F108_ZIP_SHA,
        "input_F109_artifact_sha256": F109_ZIP_SHA,
        "input_F108_status": base108["status"], "input_F109_status": base109["status"],
        "fixed_axis_ratios": ratios,
        "interior_density_ticks_1e11_g_cm3": list(INTERIOR_RHO_TICKS_1E11),
        "reused_endpoint_count": 4, "new_native_C_point_count": len(new_rows),
        "new_native_C_call_count": len(new_rows), "native_C_errors": errors,
        "series_by_fixed_ratio": series,
        "raw_journal_sha256": sha(journal.read_bytes()),
        "interpretation": (
            "This scan measures two fixed-axis-ratio mass/J slices across the interval. "
            "It is not a fixed-J sequence at interior densities and cannot prove "
            "branch identity, a physical maximum, continuum/grid convergence, "
            "dynamical stability, or photon-native EOS evidence."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8")
    print("F110_RESULT", json.dumps({
        "status": status, "new_native_C_point_count": len(new_rows),
        "new_native_C_call_count": len(new_rows),
        "mass_increment_sign_changes": {
            key: value["mass_increment_sign_change_count"] for key, value in series.items()
        },
        "native_C_errors": errors,
    }, sort_keys=True), flush=True)
    if status != "F110_FIXED_RATIO_DENSITY_SCAN_COMPLETE":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
