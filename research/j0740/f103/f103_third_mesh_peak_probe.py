#!/usr/bin/env python3
"""F103: source-native 251x501 fixed-J peak probe; never relabels a finite mesh as continuum proof."""
from __future__ import annotations
import argparse, hashlib, json, math, subprocess, sys, zipfile
from pathlib import Path
from scipy.optimize import brentq
import numpy as np

F102_ZIP_SHA = "d52c186306c8a7bda8a1490fd61a68b7eb5f7fbfcd201ad1b0c21ba2af301f1a"
F102_JSON = "F102_ORIGINAL_24_PLUS_F101_1_PLUS_F102_3_REAL_C_STARS.json"
F102_RECEIPT = "F102_PHYSICAL_C_ALL_SOURCE_SHA256_RECEIPT.json"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
TARGET_J = 4.8245626795750385e48
J_REL_TOL = 3e-5
GRID = "251x501"
RHO = np.array([2.55e15, 2.62e15, 2.69e15, 2.76e15, 2.83e15, 2.90e15, 2.97e15])
RATIOS = (0.999, 0.995, 0.990, 0.985, 0.980, 0.975, 0.970, 0.965,
          0.960, 0.950, 0.940, 0.925, 0.910, 0.890)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_baseline(path: Path) -> dict:
    raw = path.read_bytes()
    if sha(raw) != F102_ZIP_SHA:
        raise ValueError("F102_ARTIFACT_ZIP_SHA256_MISMATCH")
    with zipfile.ZipFile(path) as z:
        receipt = json.loads(z.read(F102_RECEIPT))
        meta = receipt.get(F102_JSON)
        payload = z.read(F102_JSON)
        if not meta or meta.get("sha256") != sha(payload) or meta.get("bytes") != len(payload):
            raise ValueError("F102_SOURCE_JSON_RECEIPT_MISMATCH")
        data = json.loads(payload)
    if data.get("status") != "28_OF_28_ACTUAL_C_STARS_ACROSS_TWO_MESHES_SOURCE_FIXED_J_DISCRETE_TURN_ONLY":
        raise ValueError("F102_28_STAR_BASELINE_NOT_ACCEPTED")
    if data.get("same_F99_derived_cold_EOS_sha256") != EOS_SHA:
        raise ValueError("F99_EOS_SHA_MISMATCH")
    if data.get("same_target_J_cgs") != TARGET_J:
        raise ValueError("FIXED_J_TARGET_CHANGED")
    for name, grid in data.get("both_native_C_grids", {}).items():
        stars = grid["stars"]
        if len(stars) != 14 or [s["source_point_index"] for s in stars] != list(range(14)):
            raise ValueError("F102_BASELINE_GRID_INCOMPLETE_" + name)
        if any(not s["real_solver_checked"] or s["J_relative_error"] > J_REL_TOL for s in stars):
            raise ValueError("F102_BASELINE_REAL_C_J_GATE_FAIL_" + name)
    return data

def call_rns(binary: Path, eos: Path, rho: float, ratio: float) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "f81"))
    from f81_exact_mass_spin import parse_rns
    cmd = [str(binary.resolve()), "-f", str(eos), "-e", f"{rho:.14e}", "-r", f"{ratio:.12f}"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if p.returncode != 0:
        raise RuntimeError("RNS_NATIVE_C_FAILED " + p.stdout[-240:] + p.stderr[-240:])
    star = parse_rns(p.stdout)
    if abs(star["rho_c_g_cm3"] / rho - 1.0) > 1e-9:
        raise ValueError("NATIVE_C_CENTRAL_DENSITY_MISMATCH")
    return star

def solve_one(binary: Path, eos: Path, rho: float, journal: Path, index: int) -> dict:
    trials = []
    def evaluate(ratio: float) -> float:
        star = call_rns(binary, eos, rho, ratio)
        row = {
            "mesh": GRID, "index": index, "rho_g_cm3": rho,
            "r_ratio": ratio, "M_msun": star["M_msun"],
            "R_eq_km": star["R_equatorial_km"], "f_hz": star["spin_hz"],
            "J_cgs": star["J_cgs"], "J_relative_error": abs(star["J_cgs"] / TARGET_J - 1.0),
            "real_native_RNS_C": True
        }
        trials.append(row)
        with journal.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, allow_nan=False) + "\n")
        return star["J_cgs"] / TARGET_J - 1.0
    previous = None
    bracket = None
    selected = None
    for ratio in RATIOS:
        error = evaluate(ratio)
        if abs(error) <= J_REL_TOL:
            selected = ratio
            break
        if previous is not None and previous[1] * error < 0:
            bracket = (previous[0], ratio)
            break
        previous = (ratio, error)
    if bracket is None and selected is None:
        raise RuntimeError("NATIVE_C_FIXED_J_BRACKET_NOT_FOUND")
    if bracket is not None:
        root = brentq(evaluate, *sorted(bracket), xtol=1e-10, rtol=5e-13, maxiter=65)
        error = evaluate(root)
        selected = root
    if selected is None or abs(error) > J_REL_TOL:
        raise RuntimeError("NATIVE_C_FIXED_J_TOLERANCE_FAIL")
    final = next((t for t in reversed(trials) if math.isclose(t["r_ratio"], selected, rel_tol=0, abs_tol=1e-12)), None)
    if final is None:
        raise RuntimeError("FINAL_NATIVE_C_RECEIPT_MISSING")
    return {
        "index": index, "rho_g_cm3": rho, "r_ratio": selected,
        "M_msun": final["M_msun"], "R_eq_km": final["R_eq_km"],
        "f_hz": final["f_hz"], "J_cgs": final["J_cgs"],
        "J_relative_error": final["J_relative_error"],
        "native_C_evaluations": len(trials), "real_native_RNS_C": True,
        "journal_rows": len(trials)
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--f102", type=Path, required=True)
    ap.add_argument("--eos", type=Path, required=True)
    ap.add_argument("--rns", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    baseline = read_baseline(a.f102)
    if sha(a.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA_MISMATCH")
    if not a.rns.is_file() or not a.eos.is_file() or len(str(a.eos)) > 60:
        raise ValueError("RNS_BINARY_EOS_MISSING_OR_PATH_TOO_LONG")
    if a.out.with_suffix(".jsonl").exists():
        raise FileExistsError("NEVER_OVERWRITE_F103_RAW_C_JOURNAL")
    journal = a.out.with_suffix(".jsonl")
    rows, errors = [], []
    for i, rho in enumerate(RHO):
        try:
            row = solve_one(a.rns, a.eos, float(rho), journal, i)
            rows.append(row)
            print("F103_NATIVE_C_FIXED_J_PASS", i, row["M_msun"], row["J_relative_error"], row["native_C_evaluations"], flush=True)
        except Exception as exc:
            errors.append({"index": i, "rho_g_cm3": float(rho), "error": repr(exc)})
            print("F103_NATIVE_C_POINT_FAIL_RETAINED", i, repr(exc), flush=True)
    slopes = np.diff([r["M_msun"] for r in rows]) / np.diff([r["rho_g_cm3"] / 1e15 for r in rows]) if len(rows) > 1 else np.array([])
    has_both_slope_signs = bool(np.any(slopes > 0) and np.any(slopes < 0))
    peak_idx = int(np.argmax([r["M_msun"] for r in rows])) if rows else None
    local_turn_pass = bool(len(rows) == len(RHO) and peak_idx is not None and 0 < peak_idx < len(rows)-1 and has_both_slope_signs)
    status = "THIRD_MESH_LOCAL_SAMPLED_TURN_PASS" if not errors and local_turn_pass else "FAIL_CLOSED"
    out = {
        "schema": "J0740_F103_NATIVE_C_RNS_251x501_LOCAL_FIXED_J_PEAK_PROBE_V1",
        "status": status, "mesh": GRID, "EOS_sha256": EOS_SHA,
        "target_J_cgs": TARGET_J, "J_relative_tolerance": J_REL_TOL,
        "F102_artifact_sha256": F102_ZIP_SHA,
        "F102_old_28_stars_reused_without_rerun": True,
        "new_native_C_stars": rows, "native_C_errors": errors,
        "slope_Msun_per_1e15g_cm3": slopes.tolist(),
        "local_sampled_peak_index": peak_idx,
        "local_sampled_peak": rows[peak_idx] if peak_idx is not None else None,
        "local_turn_sign_change": has_both_slope_signs,
        "local_turn_gate": local_turn_pass,
        "baseline_two_mesh_peaks": {
            g: v["measured_slope"] for g, v in baseline["both_native_C_grids"].items()
        },
        "claim_limit": "A third finite mesh and seven local density samples do not prove a continuous turning point, a rotating dynamical eigenmode, or full seven-original-EOS X-PSI photon Bayes evidence.",
        "new_native_C_call_count": int(sum(r["native_C_evaluations"] for r in rows)),
        "journal_sha256": sha(journal.read_bytes()) if journal.exists() else None
    }
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print("F103_RESULT", json.dumps({"status": status, "new_C_calls": out["new_native_C_call_count"], "peak": out["local_sampled_peak"], "slopes": out["slope_Msun_per_1e15g_cm3"]}, sort_keys=True), flush=True)
    if status != "THIRD_MESH_LOCAL_SAMPLED_TURN_PASS":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
