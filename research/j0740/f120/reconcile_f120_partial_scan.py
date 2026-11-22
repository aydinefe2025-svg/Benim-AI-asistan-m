#!/usr/bin/env python3
"""Reconcile F120's fail-closed package from its preserved native C journal."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path

from research.j0740.f120 import f120_fine_mesh_fixedj as f120

PARTIAL_ZIP_SHA = "dc4db66f8a377cf7b4ce6f0fb4b148f73c6e93fd7f2e3c9302d978d9f97ef1f0"
PARTIAL_STATUS = "FAIL_CLOSED"
GRID = "3001x6001"
RHO_POINTS = (2622286500000000, 2622286750000000, 2622287000000000)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--partial", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    partial_bytes = args.partial.read_bytes()
    if sha(partial_bytes) != PARTIAL_ZIP_SHA:
        raise ValueError("F120_PARTIAL_ARTIFACT_SHA256_MISMATCH")
    with zipfile.ZipFile(args.partial) as archive:
        if archive.testzip() is not None:
            raise ValueError("F120_PARTIAL_ARTIFACT_CRC_FAILURE")
        f119_bytes = archive.read("F119/F119_artifact.zip")
        old_result = json.loads(archive.read("F120/F120_FINE_MESH_FIXEDJ.json"))
        journal_bytes = archive.read("F120/F120_FINE_MESH_FIXEDJ.jsonl")
        binary_text = archive.read("F120/F120_FINE_MESH_NATIVE_C_BINARY_SHA256.txt").decode("utf-8").strip()

    if sha(f119_bytes) != f120.F119_ZIP_SHA:
        raise ValueError("F120_PARTIAL_NESTED_F119_SHA256_MISMATCH")
    with tempfile.NamedTemporaryFile(suffix=".zip") as baseline:
        baseline.write(f119_bytes)
        baseline.flush()
        f119_result, _ = f120.read_f119(Path(baseline.name))

    if sha(journal_bytes) != old_result.get("raw_journal_sha256"):
        raise ValueError("F120_PARTIAL_RAW_JOURNAL_SHA256_MISMATCH")
    rows = [json.loads(line) for line in journal_bytes.decode("utf-8").splitlines() if line.strip()]
    if (old_result.get("status") != PARTIAL_STATUS
            or old_result.get("diagnostic_only") is not True
            or old_result.get("mesh") != GRID
            or old_result.get("baseline_mesh") != f120.BASE_GRID
            or old_result.get("EOS_sha256") != f120.EOS_SHA
            or old_result.get("target_J_cgs") != f120.f106.TARGET_J
            or old_result.get("J_relative_tolerance") != f120.f106.J_REL_TOL
            or old_result.get("pinned_RNS_upstream_commit") != f120.RNS_COMMIT
            or old_result.get("input_F119_artifact_sha256") != f120.F119_ZIP_SHA
            or old_result.get("native_C_call_count") != 18
            or len(rows) != 18
            or old_result.get("native_C_errors") != [{
                "error": "KeyError(2622286750000000)",
                "local_ratio_bracket": [0.990076936835, 0.990276936835],
                "native_C_evaluations": 6,
                "rho_g_cm3": 2622286750000000,
            }]):
        raise ValueError("F120_PARTIAL_RESULT_METADATA_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}  rns3001/rns", binary_text):
        raise ValueError("F120_NATIVE_C_BINARY_HASH_RECORD_INVALID")
    if any(row.get("mesh") != GRID or row.get("real_native_RNS_C") is not True
           or row.get("error") for row in rows):
        raise ValueError("F120_RAW_NATIVE_C_ROW_INVALID")
    if tuple(sorted({int(row["rho_g_cm3"]) for row in rows})) != RHO_POINTS:
        raise ValueError("F120_RAW_DENSITY_POINTS_MISMATCH")
    grouped = {rho: [row for row in rows if row["rho_g_cm3"] == rho] for rho in RHO_POINTS}
    if any(len(grouped[rho]) != 6 for rho in RHO_POINTS):
        raise ValueError("F120_RAW_TRIAL_COUNT_PER_DENSITY_MISMATCH")

    best = {rho: min(grouped[rho], key=lambda row: row["J_relative_error"]) for rho in RHO_POINTS}
    for rho, row in best.items():
        if row.get("within_target_tolerance") is not True or row["J_relative_error"] > f120.f106.J_REL_TOL:
            raise ValueError("F120_RECONCILED_ROOT_OUTSIDE_TARGET_J_TOLERANCE")
    partial_roots = {int(row["rho_g_cm3"]): row for row in old_result["fixed_J_solutions"]}
    if set(partial_roots) != {RHO_POINTS[0], RHO_POINTS[-1]}:
        raise ValueError("F120_PARTIAL_ENDPOINT_ROOTS_MISSING")
    for rho in (RHO_POINTS[0], RHO_POINTS[-1]):
        root = partial_roots[rho]
        row = best[rho]
        for key, actual_key in (("M_msun", "M_msun"), ("R_eq_km", "R_eq_km"),
                                ("J_relative_error", "J_relative_error"),
                                ("selected_r_ratio", "r_ratio_C_input")):
            if root.get(key) != row.get(actual_key):
                raise ValueError("F120_PARTIAL_ENDPOINT_ROOT_JOURNAL_MISMATCH")

    f119_roots = {int(row["rho_g_cm3"]): row for row in f119_result["fixed_J_solutions"]}
    low, high = f119_roots[RHO_POINTS[0]], f119_roots[RHO_POINTS[-1]]
    fraction = (RHO_POINTS[1]-RHO_POINTS[0])/(RHO_POINTS[-1]-RHO_POINTS[0])
    baseline_at_mid = {
        "M_msun": low["M_msun"] + fraction*(high["M_msun"]-low["M_msun"]),
        "R_eq_km": low["R_eq_km"] + fraction*(high["R_eq_km"]-low["R_eq_km"]),
    }
    f119_reference = {RHO_POINTS[0]: low, RHO_POINTS[1]: baseline_at_mid, RHO_POINTS[-1]: high}

    solutions = []
    for rho in RHO_POINTS:
        row = best[rho]
        reference = f119_reference[rho]
        solutions.append({
            "rho_g_cm3": rho, "selected_r_ratio": row["r_ratio_C_input"],
            "M_msun": row["M_msun"], "R_eq_km": row["R_eq_km"],
            "f_hz": row["f_hz"], "J_cgs": row["J_cgs"],
            "J_relative_error": row["J_relative_error"],
            "native_C_evaluations": len(grouped[rho]), "real_native_RNS_C": True,
            "mesh": GRID, "baseline_mesh": f120.BASE_GRID,
            "F119_baseline_M_msun": reference["M_msun"],
            "F119_baseline_R_eq_km": reference["R_eq_km"],
            "mesh_delta_M_msun": row["M_msun"]-reference["M_msun"],
            "mesh_delta_R_eq_km": row["R_eq_km"]-reference["R_eq_km"],
            "recovered_from_original_native_journal": True,
        })

    mass_steps = []
    for a, b in zip(solutions, solutions[1:]):
        f119_dm = b["F119_baseline_M_msun"]-a["F119_baseline_M_msun"]
        f120_dm = b["M_msun"]-a["M_msun"]
        mass_steps.append({
            "rho_low_g_cm3": a["rho_g_cm3"], "rho_high_g_cm3": b["rho_g_cm3"],
            "F119_mass_delta_msun": f119_dm, "F120_mass_delta_msun": f120_dm,
            "mass_delta_change_msun": f120_dm-f119_dm,
            "F120_to_F119_mass_delta_ratio": f120_dm/f119_dm if f119_dm else None,
        })
    reconciled_journal = args.out.with_suffix(".jsonl")
    reconciled_journal.parent.mkdir(parents=True, exist_ok=True)
    if reconciled_journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F120_RECONCILED_JOURNAL")
    reconciled_journal.write_bytes(journal_bytes)

    out = {
        "schema": "J0740_F120_RECONCILED_NATIVE_C_FINE_MESH_FIXEDJ_V1",
        "status": "F120_PARTIAL_SCAN_RECONCILED_DIAGNOSTIC_COMPLETE",
        "diagnostic_only": True, "mesh": GRID, "baseline_mesh": f120.BASE_GRID,
        "EOS_sha256": f120.EOS_SHA, "target_J_cgs": f120.f106.TARGET_J,
        "J_relative_tolerance": f120.f106.J_REL_TOL,
        "pinned_RNS_upstream_commit": f120.RNS_COMMIT,
        "native_C_binary_sha256": binary_text.split()[0],
        "input_F119_artifact_sha256": f120.F119_ZIP_SHA,
        "input_F119_status": f119_result["status"],
        "input_F120_partial_artifact_sha256": PARTIAL_ZIP_SHA,
        "input_F120_partial_status": PARTIAL_STATUS,
        "density_points_g_cm3": list(RHO_POINTS),
        "native_C_call_count": len(rows),
        "reconciliation_added_native_C_call_count": 0,
        "trial_rows": rows, "fixed_J_solutions": solutions,
        "mass_steps": mass_steps, "native_C_errors": [],
        "original_packaging_error": "KeyError at unsampled midpoint baseline lookup; original artifact retained",
        "raw_journal_sha256": sha(journal_bytes),
        "interpretation": (
            "All three fixed-J roots were reconstructed from the original 18-row native C journal; "
            "no new native C calculations were run during reconciliation. The sampled mass feature "
            "persists on one finer mesh, but this two-mesh sensitivity check is not formal convergence "
            "and establishes no physical cause, branch identity, physical maximum, rotating-star "
            "stability, or photon-native EOS evidence."
        ),
    }
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print("F120_RECONCILED_RESULT", json.dumps({
        "status": out["status"], "native_C_call_count": len(rows),
        "fixed_J_solutions": solutions, "mass_steps": mass_steps,
        "native_C_errors": out["native_C_errors"],
    }, sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
