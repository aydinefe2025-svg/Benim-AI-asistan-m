#!/usr/bin/env python3
"""F107: dense local density scan using pinned native RNS C and fixed J."""
from __future__ import annotations
import argparse, hashlib, json, math, sys, zipfile
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from research.j0740.f106 import f106_sixth_mesh_peak_probe as f106

F106_ZIP_SHA = "c114b73fda17a4822cb656b624fc41babee85785e476a5e09edf38ae5680a407"
F106_RESULT = "F106/F106_501x1001_LOCAL_PEAK.json"
F106_JOURNAL = "F106/F106_501x1001_LOCAL_PEAK.jsonl"
GRID = "501x1001"
RHO = np.array([2.56e15, 2.57e15, 2.58e15, 2.59e15, 2.60e15, 2.61e15,
                2.63e15, 2.64e15, 2.65e15, 2.66e15, 2.67e15, 2.68e15,
                2.70e15, 2.71e15])

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_f106(path: Path) -> dict:
    raw = path.read_bytes()
    if sha(raw) != F106_ZIP_SHA:
        raise ValueError("F106_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as z:
        result = json.loads(z.read(F106_RESULT))
        journal_bytes = z.read(F106_JOURNAL)
        if sha(journal_bytes) != result.get("journal_sha256"):
            raise ValueError("F106_RAW_JOURNAL_SHA_MISMATCH")
        journal = [json.loads(line) for line in journal_bytes.decode().splitlines()]
        stars = result.get("new_native_C_stars", [])
        if result.get("status") != "SIXTH_MESH_LOCAL_SAMPLED_TURN_PASS":
            raise ValueError("F106_NOT_ACCEPTED_AS_SAMPLE_BASELINE")
        if result.get("mesh") != GRID or result.get("EOS_sha256") != f106.EOS_SHA:
            raise ValueError("F106_PHYSICAL_INPUT_OR_GRID_MISMATCH")
        if result.get("target_J_cgs") != f106.TARGET_J or result.get("J_relative_tolerance") != f106.J_REL_TOL:
            raise ValueError("F106_FIXED_J_ACCEPTANCE_CHANGED")
        if len(stars) != 7 or len(journal) != 70 or result.get("new_native_C_call_count") != 70:
            raise ValueError("F106_BASELINE_RECEIPT_COUNTS_MISMATCH")
        if result.get("native_C_errors"):
            raise ValueError("F106_BASELINE_HAS_NATIVE_C_ERRORS")
        if any(row.get("mesh") != GRID or not row.get("real_native_RNS_C") for row in journal):
            raise ValueError("F106_BASELINE_NOT_NATIVE_C")
        for star in stars:
            group = [row for row in journal if row.get("index") == star["index"]]
            if len(group) != star["native_C_evaluations"] or len(group) != 10:
                raise ValueError("F106_BASELINE_PER_STAR_CALL_COUNT_MISMATCH")
            if not any(math.isclose(row["r_ratio"], star["r_ratio"], rel_tol=0, abs_tol=1e-12)
                       and math.isclose(row["M_msun"], star["M_msun"], rel_tol=0, abs_tol=1e-12)
                       and abs(row["J_cgs"]-star["J_cgs"])/star["J_cgs"] < 1e-14 for row in group):
                raise ValueError("F106_FINAL_C_ROOT_NOT_PRESENT_IN_JOURNAL")
            if star["J_relative_error"] > f106.J_REL_TOL:
                raise ValueError("F106_FINAL_J_ACCEPTANCE_FAIL")
    return result

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f103", type=Path, required=True)
    ap.add_argument("--f104", type=Path, required=True)
    ap.add_argument("--f105", type=Path, required=True)
    ap.add_argument("--f106", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    prior3, base = f106.read_baseline(a.f103)
    prior4 = f106.read_f104(a.f104)
    prior5 = f106.read_f105_failed(a.f105)
    prior6 = read_f106(a.f106)
    if sha(a.eos.read_bytes()) != f106.EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA_MISMATCH")
    if not a.rns.is_file() or len(str(a.eos)) > 60:
        raise ValueError("RNS_OR_EOS_MISSING_OR_PATH_TOO_LONG")
    journal = a.out.with_suffix(".jsonl")
    if journal.exists():
        raise FileExistsError("NEVER_OVERWRITE_F107_RAW_C_JOURNAL")

    new_rows, errors = [], []
    for i, rho in enumerate(RHO):
        try:
            row = f106.solve_one(a.rns, a.eos, float(rho), journal, i)
            new_rows.append(row)
            print("F107_NATIVE_C_FIXED_J_PASS", i, row["rho_g_cm3"], row["M_msun"],
                  row["J_relative_error"], row["native_C_evaluations"], flush=True)
        except Exception as exc:
            errors.append({"index": i, "rho_g_cm3": float(rho), "error": repr(exc)})
            print("F107_NATIVE_C_POINT_FAIL_RETAINED", i, repr(exc), flush=True)

    reference_rows = prior6["new_native_C_stars"]
    combined = sorted(reference_rows + new_rows, key=lambda row: row["rho_g_cm3"])
    densities = [row["rho_g_cm3"] for row in combined]
    if len(set(densities)) != len(densities):
        raise ValueError("F107_DUPLICATE_DENSITY_RECORD")
    slopes = np.diff([row["M_msun"] for row in combined]) / np.diff(np.asarray(densities) / 1e15)
    peak_index = int(np.argmax([row["M_msun"] for row in combined])) if combined else None
    turn = bool(peak_index is not None and 0 < peak_index < len(combined)-1
                and np.any(slopes[:peak_index] > 0) and np.any(slopes[peak_index:] < 0))
    status = "DENSE_LOCAL_SCAN_PASS" if len(new_rows) == len(RHO) and not errors and turn else "FAIL_CLOSED"
    out = {
        "schema": "J0740_F107_NATIVE_C_RNS_501x1001_DENSE_LOCAL_FIXED_J_SCAN_V1",
        "status": status, "mesh": GRID, "EOS_sha256": f106.EOS_SHA,
        "target_J_cgs": f106.TARGET_J, "J_relative_tolerance": f106.J_REL_TOL,
        "F103_artifact_sha256": f106.F103_ZIP_SHA,
        "F104_artifact_sha256": f106.F104_ZIP_SHA,
        "F105_failed_artifact_sha256": f106.F105_ZIP_SHA,
        "F106_reference_artifact_sha256": F106_ZIP_SHA,
        "F106_reference_validated": True,
        "F103_F104_F105_validation_completed": True,
        "reused_F106_reference_stars_without_rerun": 7,
        "new_density_points_count": len(new_rows),
        "new_native_C_call_count": sum(row["native_C_evaluations"] for row in new_rows),
        "new_native_C_stars": new_rows, "native_C_errors": errors,
        "combined_local_samples_with_F106_reference": combined,
        "combined_local_slopes_Msun_per_1e15g_cm3": slopes.tolist(),
        "combined_sampled_peak_index": peak_index,
        "combined_sampled_peak": combined[peak_index] if peak_index is not None else None,
        "combined_local_turn_gate": turn,
        "journal_sha256": sha(journal.read_bytes()) if journal.exists() else None,
        "claim_limit": "This is a denser finite-grid sampled turning-point scan on the derived F99 EOS. It does not establish continuum/grid convergence, rotating dynamical eigenmodes, or full original-seven-EOS X-PSI photon Bayes evidence.",
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    print("F107_RESULT", json.dumps({"status": status, "new_points": len(new_rows),
          "new_C_calls": out["new_native_C_call_count"], "peak": out["combined_sampled_peak"],
          "slope_sign_change": turn}, sort_keys=True), flush=True)
    if status != "DENSE_LOCAL_SCAN_PASS":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
