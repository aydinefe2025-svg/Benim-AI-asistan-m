"""F53 source-locked true C-RNS constant-angular-momentum WFF1 sequence.

One *specified* J is obtained from direct regeneration of the F52 C-RNS
f=346.536369 Hz reference at central density 2.90e15 g/cm3.
At each new central density we solve direct RNS angular momentum J=constant
by bracketing axial ratio, then detect an M(rho_c)|J sampled turnover.
This is NOT a proof of global nonlinear/dynamical stability or a certified
original nuclear WFF1 EOS. The F42 EOS source has a causal-lift assumption.
M0/baryon density normalization is NOT physically established.
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "f52"))
sys.path.insert(0, str(HERE.parent / "physical_eos"))
from f52_wff1_turnover_scan import source_lock, SPIN_HZ
from apr4_causal_fixed_J_turning import run_one, patch_rns_source

PINNED_RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
F52_CI_SHA256 = "68c72ac72783f55d514483215c893f17084bfe672ea55121af66810d71e17650"
ANCHOR_EC = 2.900e15
RNS_TARGET_J_REL_TOL = 1e-5
COARSE_E15 = (2.20, 2.35, 2.50, 2.65, 2.75, 2.80, 2.85, 2.90,
              2.95, 3.00, 3.05, 3.10, 3.20, 3.30, 3.45, 3.60, 3.80, 4.00)


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def locked_f52_source(path):
    if sha256(path) != F52_CI_SHA256:
        raise ValueError("SOURCE_F52_CI_ARTIFACT_SHA_MISMATCH")
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            raise ValueError("SOURCE_F52_ZIP_CRC_FAIL")
        data = json.loads(z.read("F52_WFF1_direct_fixed_spin_turnover.json"))
        if data.get("status") != "DIRECT_C_FIXED_F_TURNOVER_BRACKETED_NOT_FIXED_J_STABILITY":
            raise ValueError("F52_SOURCE_NOT_COMPLETED")
        stars = data.get("real_direct_C_stars", [])
        if len(stars) != 27:
            raise ValueError("F52_SOURCE_EXPECT_27_REAL_C_STARS")
        found = [s for s in stars if abs(s["central_energy_density_g_cm3"] - ANCHOR_EC) < 1e5]
        if len(found) != 1 or abs(found[0]["spin_hz"] - SPIN_HZ) > .02:
            raise ValueError("F52_SOURCE_ANCHOR_NOT_UNIQUE")
        return found[0], data


def solve_at_J(eval_star, ec, target_j, guess_ratio, trace=None):
    """Brent in axial ratio; each value is a directly computed C-RNS star."""
    if trace is None:
        trace = []
    if not (math.isfinite(target_j) and 1e44 < target_j < 1e52):
        raise ValueError("NONPHYSICAL_TARGET_J")
    if not (.85 <= guess_ratio <= 1.0 and 0.2e15 < ec < 4.5e15):
        raise ValueError("INVALID_FIXED_J_SEARCH_DOMAIN")
    cache = {}

    def probe(ratio):
        key = round(float(ratio), 10)
        if key not in cache:
            try:
                star = eval_star(ec, key)
                j = float(star["J_cgs"])
                if not (math.isfinite(j) and j >= 0 and math.isfinite(star["mass_msun"])):
                    raise ValueError("NONFINITE_OR_NEGATIVE_J")
                err = j / target_j - 1.0
                cache[key] = (err, star)
                trace.append({"ratio": key, "relative_J_residual": err,
                              "mass_msun": float(star["mass_msun"]), "status": "DIRECT_C_OK"})
            except Exception as exc:
                cache[key] = None
                trace.append({"ratio": key, "status": "DIRECT_C_FAIL",
                              "failure": type(exc).__name__ + ": " + str(exc)[:210]})
        return cache[key]

    bracket = None
    for delta in (.0015, .004, .012, .035, .075):
        lo, hi = max(.85, guess_ratio - delta), min(1.0, guess_ratio + delta)
        a, b = probe(lo), probe(hi)
        if a is not None and b is not None and a[0] * b[0] <= 0.0:
            bracket = (lo, hi)
            break
    if bracket is None:
        grid = sorted(set((.85, .90, .94, .96, .975, .985, .990, .995, .998, 1.0, guess_ratio)))
        data = [(r, probe(r)) for r in grid]
        good = [(r, record) for r, record in data if record is not None]
        bracket = next(((lo, hi) for (lo, a), (hi, b) in zip(good, good[1:])
                        if a[0] * b[0] <= 0.0), None)
    if bracket is None:
        raise ValueError("NO_DIRECT_C_CONSTANT_J_BRACKET")
    lo, hi = bracket
    ratio = float(brentq(lambda x: probe(x)[0], lo, hi,
                         xtol=2e-10, rtol=2e-10, maxiter=48))
    final = probe(ratio)
    if final is None or abs(final[0]) > RNS_TARGET_J_REL_TOL:
        raise ValueError("DIRECT_C_FIXED_J_RESIDUAL_FAIL")
    return {**final[1], "relative_J_residual": final[0],
            "bracket_ratio": [lo, hi], "C_evaluations": len(cache)}, trace


def turnover(sequence):
    good = sorted([s for s in sequence if s.get("status") == "DIRECT_C_FIXED_J_PASS"],
                  key=lambda s: s["ec_g_cm3"])
    if len(good) < 8:
        return {"status": "INSUFFICIENT_DIRECT_C_STARS", "number_good": len(good),
                "constant_J": True, "dynamical_stability": "NOT_TESTED"}
    imax = max(range(len(good)), key=lambda i: good[i]["mass_msun"])
    peak = good[imax]
    bracketed = (2 <= imax <= len(good) - 3
                 and good[imax - 1]["mass_msun"] < peak["mass_msun"]
                 and good[imax + 1]["mass_msun"] < peak["mass_msun"])
    return {
        "status": "SAMPLED_CONSTANT_J_MASS_TURNOVER_BRACKETED" if bracketed
                  else "UNBRACKETED_CONSTANT_J_MASS_MAXIMUM",
        "number_good": len(good),
        "sampled_peak_M_msun": peak["mass_msun"],
        "sampled_peak_ec_g_cm3": peak["ec_g_cm3"],
        "sampled_peak_R_eq_km": peak["radius_eq_km"],
        "sampled_peak_spin_hz": peak["spin_hz"],
        "sampled_peak_ratio": peak["axis_ratio"],
        "neighbor_masses": [good[imax-1]["mass_msun"] if imax else None,
                            peak["mass_msun"],
                            good[imax+1]["mass_msun"] if imax+1 < len(good) else None],
        "neighbor_ec_g_cm3": [good[imax-1]["ec_g_cm3"] if imax else None,
                              peak["ec_g_cm3"],
                              good[imax+1]["ec_g_cm3"] if imax+1 < len(good) else None],
        "RNS_M0_physical_interpretation": "NOT_ESTABLISHED",
        "global_branch_completeness": "NOT_ESTABLISHED",
        "dynamical_stability": "NOT_TESTED",
        "physical_nuclear_EOS_validity": "NOT_ESTABLISHED",
    }


def run(f44, f46, f52, binary, work, output, patch):
    table, prior_anchor, original = source_lock(f44, f46, work)
    f52_anchor, f52_source = locked_f52_source(f52)
    if abs(prior_anchor["mass_msun"] - 2.1) > .0001:
        raise ValueError("F46_PINNED_ANCHOR_DRIFT")
    patchdata = json.loads(Path(patch).read_text())
    if patchdata.get("patched_sha256") is None or patchdata.get("replacements") != 1:
        raise ValueError("F53_PINNED_C_PRINT_PATCH_NOT_ESTABLISHED")
    if patchdata.get("printed_J_cgs_symbol") != "star.ang_mom":
        raise ValueError("F53_WRONG_J_SOURCE_SYMBOL")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "J0740_F53_WFF1_REAL_PINNED_RNS_CONSTANT_J_v1",
        "status": "STARTED",
        "RNS_upstream_commit": PINNED_RNS_COMMIT,
        "F44_archive_sha256": sha256(f44),
        "F46_WFF1_failed_archive_sha256": sha256(f46),
        "F52_CI_source_sha256": sha256(f52),
        "RNS_C_binary_sha256": sha256(binary),
        "WFF1_EOS_table_sha256": sha256(table),
        "C_diagnostic_patch": patchdata,
        "original_F52_fixed_f_peak_M_msun": f52_source["turnover_diagnostic"]["max_sampled_mass_msun"],
        "original_F52_peak_input_star": f52_anchor,
        "RNS_M0_source_n_absolute_baryon_mass": "NOT_ESTABLISHED_DO_NOT_USE",
        "fixed_J_turning_criterion": "SAMPLED_AXISYMMETRIC_SECULAR_TURNOVER_DIAGNOSTIC_NOT_NONLINEAR_STABILITY_PROOF",
        "physical_WFF1_original_nuclear_EOS": "NOT_ESTABLISHED_F42_IS_NEW_LIFTED_HYPOTHESIS",
        "seven_EOS_Bayes": "NOT_RUN",
        "direct_C_constant_J_stars": [],
        "failed_centers": [],
    }
    def save():
        output.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n")

    save()
    try:
        # EXACT F52 direct star regenerated using the genuine same pinned RNS physics code.
        anchor = run_one(binary, table, ANCHOR_EC, f52_anchor["axis_ratio"])
        if not (abs(anchor["mass_msun"] - f52_anchor["mass_msun"]) < 1e-7
                and abs(anchor["radius_eq_km"] - f52_anchor["radius_eq_km"]) < 1e-6
                and abs(anchor["spin_hz"] - f52_anchor["spin_hz"]) < 1e-4):
            raise ValueError("F53_REGRESSION_DIRECT_F52_ANCHOR_DRIFT")
        target_j = anchor["J_cgs"]
        if not 1e44 < target_j < 1e52:
            raise ValueError("F53_ANCHOR_REAL_C_J_OUT_OF_BOUNDS")
        report["regenerated_F52_reference"] = anchor
        report["constant_target_J_cgs"] = target_j
        print("DIRECT_C_ANCHOR_REGENERATED", anchor["mass_msun"], anchor["spin_hz"], target_j, flush=True)
        save()
        solved = set()
        last_ratio = anchor["axis_ratio"]

        def sample(ec15, stage):
            nonlocal last_ratio
            ec = round(float(ec15), 8) * 1e15
            if ec in solved: return
            solved.add(ec)
            trace = []
            entry = {"ec_g_cm3": ec, "scan_stage": stage, "trace": trace}
            try:
                star, trace = solve_at_J(lambda density, ratio: run_one(binary, table, density, ratio),
                                         ec, target_j, last_ratio, trace)
                entry.update(star)
                entry["status"] = "DIRECT_C_FIXED_J_PASS"
                last_ratio = star["axis_ratio"]
                print(f"F53 {stage} ec={ec15:.5f} mass={star['mass_msun']:.10f} spin={star['spin_hz']:.6f} rel_J={star['relative_J_residual']:.3g}", flush=True)
            except Exception as exc:
                entry["status"] = "FAILED_DIRECT_C_FIXED_J"
                entry["failure"] = type(exc).__name__ + ": " + str(exc)[:320]
                report["failed_centers"].append({"ec_g_cm3":ec,"failure":entry["failure"]})
                print(f"F53 {stage} ec={ec15:.5f} FAILED {entry['failure']}", flush=True)
            report["direct_C_constant_J_stars"].append(entry)
            save()

        for ec15 in COARSE_E15:
            sample(ec15, "coarse")
        valid = [s for s in report["direct_C_constant_J_stars"] if s["status"]=="DIRECT_C_FIXED_J_PASS"]
        if valid:
            peak = max(valid, key=lambda x:x["mass_msun"])
            center = peak["ec_g_cm3"] / 1e15
            for k in range(-8, 9):
                ec15 = center + k * .025
                if .25 < ec15 < 4.5: sample(ec15, "peak_refinement")
        summary = turnover(report["direct_C_constant_J_stars"])
        report["turnover_diagnostic"] = summary
        errors = [abs(s["relative_J_residual"]) for s in report["direct_C_constant_J_stars"]
                  if s["status"]=="DIRECT_C_FIXED_J_PASS"]
        report["max_relative_J_residual"] = max(errors) if errors else None
        report["status"] = ("PASS_SAMPLED_CONSTANT_J_TURNING_DIAGNOSTIC_NOT_GLOBAL_STABILITY"
                            if summary["status"]=="SAMPLED_CONSTANT_J_MASS_TURNOVER_BRACKETED"
                            else "PARTIAL_UNCERTIFIED_CONSTANT_J_TURNING_DIAGNOSTIC")
    except Exception as exc:
        report["status"] = "FAILED_SOURCE_LOCK_OR_ANCHOR_UNCERTIFIED"
        report["fatal_error"] = type(exc).__name__ + ": " + str(exc)[:400]
        save()
        raise
    save()
    print(json.dumps({"status":report["status"],"J":report.get("constant_target_J_cgs"),
                      "summary":report.get("turnover_diagnostic"),
                      "failed":len(report["failed_centers"])},sort_keys=True),flush=True)
    return report


def main():
    p=argparse.ArgumentParser()
    for key in ("f44", "f46", "f52", "binary", "work", "out", "patch"):
        p.add_argument("--" + key, type=Path, required=True)
    a=p.parse_args()
    result=run(a.f44,a.f46,a.f52,a.binary,a.work,a.out,a.patch)
    if result["status"]!="PASS_SAMPLED_CONSTANT_J_TURNING_DIAGNOSTIC_NOT_GLOBAL_STABILITY":
        raise SystemExit(2)


if __name__=="__main__":
    main()
