"""F52: source-locked direct C-RNS fixed-frequency WFF1 mass turnover scan.

Diagnostic only. A maximum along constant frequency is NOT the turning-point
theorem at constant angular momentum J, nor proof of globally stable Mmax.
All reported stellar rows are direct C solutions, never interpolated stars.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import zipfile
from pathlib import Path
from scipy.optimize import brentq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "f44"))
import f44_seven_new_candidate_rns as rns

F44_SHA = "b45d99bf5d58179f49df12a5101b8c40204e146aef31e0987b5260d6ffd0bd98"
F46_WFF1_SHA = "bc4795ab244cc169f5ee5011c3ba1ac4646926a14c982b94d07808d647a955f3"
SPIN_HZ = 346.536369
SPIN_TOL_HZ = 0.02
FAILED_HIGH_MASSES = (2.125, 2.15, 2.175)
COARSE_E15 = (2.20, 2.35, 2.50, 2.65, 2.80, 2.95, 3.10, 3.25, 3.40, 3.55, 3.70, 3.85, 4.00)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_lock(f44, f46, work):
    if sha256(f44) != F44_SHA or sha256(f46) != F46_WFF1_SHA:
        raise ValueError("F52_PINNED_F44_OR_F46_SHA_DRIFT")
    with zipfile.ZipFile(f44) as z:
        if z.testzip() is not None:
            raise ValueError("F44_SOURCE_CRC_FAIL")
        record = json.loads(z.read("F44_direct_RNS_seven_candidates.json"))
        eos = record["eos"]["WFF1"]
        table_name = eos["model_label"] + ".rns"
        data = z.read("eos_tables/" + table_name)
        if hashlib.sha256(data).hexdigest() != eos["model_table_sha256"]:
            raise ValueError("F44_WFF1_EOS_TABLE_DRIFT")
    with zipfile.ZipFile(f46) as z:
        if z.testzip() is not None:
            raise ValueError("F46_SOURCE_CRC_FAIL")
        failed = json.loads(z.read("WFF1_fixed_spin_direct_curve.json"))
        if failed["eos"] != "WFF1" or not all(str(x) in failed["failures"] for x in FAILED_HIGH_MASSES):
            raise ValueError("F46_ORIGINAL_HIGH_MASS_FAILURES_DRIFT")
        anchor = failed["roots"]["2.1"]
        if abs(anchor["mass_msun"] - 2.1) > 1e-4 or abs(anchor["spin_hz"] - SPIN_HZ) > SPIN_TOL_HZ:
            raise ValueError("F46_2P1_DIRECT_SOURCE_ANCHOR_DRIFT")
    work.mkdir(parents=True, exist_ok=True)
    table = work / table_name
    table.write_bytes(data)
    return table, anchor, failed


def solve_fixed_frequency(eval_star, ec, guess_ratio, spin=SPIN_HZ):
    """Find a C-RNS star at one fixed central density, by bracketing axial ratio."""
    trace = []
    cache = {}

    def probe(ratio):
        ratio = min(1.0, max(.85, float(ratio)))
        key = round(ratio, 10)
        if key not in cache:
            try:
                star = eval_star(ec, key)
                delta = float(star["spin_hz"] - spin)
                if not (math.isfinite(delta) and math.isfinite(star["mass_msun"])):
                    raise ValueError("NONFINITE_STAR")
                cache[key] = (delta, star)
                trace.append({"axis_ratio": key, "spin_residual_hz": delta,
                              "mass_msun": star["mass_msun"]})
            except Exception as exc:
                cache[key] = None
                trace.append({"axis_ratio": key, "error": type(exc).__name__ + ":" + str(exc)[:200]})
        return cache[key]

    guess = min(.999, max(.855, float(guess_ratio)))
    pair = None
    for radius in (.0015, .004, .012, .035, .090):
        lo, hi = max(.85, guess - radius), min(1.0, guess + radius)
        a, b = probe(lo), probe(hi)
        if a is not None and b is not None and a[0] * b[0] <= 0:
            pair = (lo, hi)
            break
    if pair is None:
        grid = sorted(set((.85, .90, .94, .97, .98, .985, .99, .992, .995, .998, 1.0, guess)))
        valid = [(r, probe(r)) for r in grid]
        valid = [(r, x) for r, x in valid if x is not None]
        pair = next(((a, b) for (a, x), (b, y) in zip(valid, valid[1:]) if x[0] * y[0] <= 0), None)
    if pair is None:
        raise ValueError("NO_VALID_DIRECT_C_FIXED_SPIN_BRACKET")
    lo, hi = pair
    ratio = float(brentq(lambda r: probe(r)[0], lo, hi, xtol=2e-10, rtol=2e-10, maxiter=55))
    root = probe(ratio)
    if root is None or abs(root[0]) > SPIN_TOL_HZ:
        raise ValueError("DIRECT_C_FIXED_SPIN_ROOT_TOLERANCE_FAIL")
    return {**root[1], "spin_residual_hz": root[0], "direct_c_calls": len(trace),
            "bracket_ratio": [lo, hi]}, trace


def summarize_turnover(stars):
    ordered = sorted(stars, key=lambda s: s["central_energy_density_g_cm3"])
    if len(ordered) < 3:
        return {"status": "INSUFFICIENT_DIRECT_STARS", "constant_J_stability": "NOT_TESTED"}
    peak_index = max(range(len(ordered)), key=lambda i: ordered[i]["mass_msun"])
    peak = ordered[peak_index]
    left = ordered[:peak_index]
    right = ordered[peak_index + 1:]
    bracketed = bool(left and right and left[-1]["mass_msun"] < peak["mass_msun"]
                     and right[0]["mass_msun"] < peak["mass_msun"])
    highest = max(s["mass_msun"] for s in ordered)
    return {
        "status": "SAMPLED_FIXED_F_TURNOVER_BRACKETED" if bracketed else "SAMPLED_MAXIMUM_NOT_BRACKETED",
        "number_direct_C_stars": len(ordered),
        "max_sampled_mass_msun": highest,
        "max_sampled_center_density_g_cm3": peak["central_energy_density_g_cm3"],
        "max_sampled_eq_radius_km": peak["radius_eq_km"],
        "adjacent_direct_masses_msun": [
            left[-1]["mass_msun"] if left else None,
            peak["mass_msun"],
            right[0]["mass_msun"] if right else None],
        "old_failed_high_mass_targets_msun": list(FAILED_HIGH_MASSES),
        "old_targets_above_sampled_max": [x for x in FAILED_HIGH_MASSES if x > highest],
        "fixed_frequency_not_fixed_J": True,
        "constant_J_stability": "NOT_TESTED",
        "physical_maximum_mass_certification": "NOT_ESTABLISHED",
        "other_disconnected_branches": "NOT_EXCLUDED",
    }


def run(f44, f46, binary, work, out):
    table, anchor, original = source_lock(f44, f46, work)
    report = {
        "schema": "J0740_F52_WFF1_PINNED_RNS_FIXED_F_TURNOVER_V1",
        "status": "STARTED", "target_spin_hz": SPIN_HZ,
        "F44_source_zip_sha256": F44_SHA, "F46_failed_WFF1_zip_sha256": F46_WFF1_SHA,
        "F46_direct_2p1_anchor": anchor,
        "rns_binary_sha256": sha256(binary), "eos_table_sha256": sha256(table),
        "original_F46_failed_artifact_preserved": True,
        "original_F46_high_target_failures": {str(m): original["failures"][str(m)] for m in FAILED_HIGH_MASSES},
        "real_direct_C_stars": [], "failed_scan_centers": [], "scan_diagnostics": [],
        "fixed_J_global_stability": "NOT_RUN",
        "nuclear_EOS_physics_certified": False,
        "seven_model_Bayes": "NOT_RUN",
        "source_native_XPSI": "NOT_RUN",
    }
    out.parent.mkdir(parents=True, exist_ok=True)

    def save():
        out.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")

    save()
    ratio_guess = anchor["axis_ratio"]
    solved = set()

    def sample(e15, stage):
        nonlocal ratio_guess
        ec = round(float(e15), 8) * 1e15
        if ec in solved:
            return
        solved.add(ec)
        try:
            star, trace = solve_fixed_frequency(
                lambda density, ratio: rns.eval_rns(binary, table, density, ratio), ec, ratio_guess)
            if abs(star["spin_hz"] - SPIN_HZ) > SPIN_TOL_HZ:
                raise ValueError("UNVERIFIED_SPIN")
            ratio_guess = star["axis_ratio"]
            record = {**star, "stage": stage, "genuine_C_RNS_solution": True}
            report["real_direct_C_stars"].append(record)
            report["scan_diagnostics"].append({"e15": e15, "stage": stage, "calls": len(trace),
                                               "result": "DIRECT_C_STAR_PASS"})
            print(f"F52 {stage} density={e15:.5f} M={star['mass_msun']:.9f} R={star['radius_eq_km']:.7f} f={star['spin_hz']:.7f}", flush=True)
        except Exception as exc:
            report["failed_scan_centers"].append({"e15": e15, "stage": stage,
                                                  "error": type(exc).__name__ + ": " + str(exc)[:240]})
            print(f"F52 {stage} density={e15:.5f} FAIL {exc}", flush=True)
        finally:
            save()

    for ec in COARSE_E15:
        sample(ec, "coarse")
    if report["real_direct_C_stars"]:
        peak = max(report["real_direct_C_stars"], key=lambda s: s["mass_msun"])
        center = peak["central_energy_density_g_cm3"] / 1e15
        for i in range(-8, 9):
            point = center + i * .025
            if .25 < point < 4.5:
                sample(point, "near_peak_refine")

    report["turnover_diagnostic"] = summarize_turnover(report["real_direct_C_stars"])
    t = report["turnover_diagnostic"]
    report["status"] = ("DIRECT_C_FIXED_F_TURNOVER_BRACKETED_NOT_FIXED_J_STABILITY"
                        if t["status"] == "SAMPLED_FIXED_F_TURNOVER_BRACKETED" else
                        "PARTIAL_DIRECT_C_SCAN_NO_CERTIFIED_TURNOVER")
    save()
    print(json.dumps({"status": report["status"], "turnover": t}, sort_keys=True), flush=True)
    return report


def main():
    p = argparse.ArgumentParser()
    for key in ("f44", "f46", "binary", "work", "out"):
        p.add_argument("--" + key, required=True, type=Path)
    a = p.parse_args()
    result = run(a.f44, a.f46, a.binary, a.work, a.out)
    if result["status"] != "DIRECT_C_FIXED_F_TURNOVER_BRACKETED_NOT_FIXED_J_STABILITY":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
