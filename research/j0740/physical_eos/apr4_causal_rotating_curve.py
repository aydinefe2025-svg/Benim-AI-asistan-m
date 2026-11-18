"""Direct RNS fixed-frequency curve and conditional F38 evidence diagnostic."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator, RegularGridInterpolator
from scipy.optimize import brentq
from scipy.stats import truncnorm

HERE = Path(__file__).resolve().parent
PHYS = HERE
ROT = HERE.parent / "rotating_gr"
sys.path.insert(0, str(PHYS))
sys.path.insert(0, str(ROT))
import apr4_causal_rns_root as causal
import precise_apr4_mass_spin_root as precise

TARGET_HZ = 346.536369
M_MU, M_SIG = 2.082, 0.0703
M_MIN, M_MAX = M_MU - 5 * M_SIG, M_MU + 5 * M_SIG
RATIOS = (1.0, .998, .996, .994, .992, .990, .988, .986, .984,
          .982, .980, .975, .970, .960, .950, .930, .900)
BANDWIDTHS = ((.015, .20), (.025, .35), (.040, .50))
F38_RUN_ID = "44120237417"
F38_ARTIFACT = "j0740-F38-published-source-marginalized-mr-likelihood"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def run_rns(binary: Path, table: Path, ec_g_cm3: float, ratio: float) -> dict:
    proc = subprocess.run(
        [str(binary.resolve()), "-f", "./" + table.name, "-e",
         f"{ec_g_cm3:.12g}", "-r", f"{ratio:.10f}"],
        cwd=table.parent, capture_output=True, text=True, timeout=180,
        check=False,
    )
    if proc.returncode:
        raise RuntimeError(f"RNS exit={proc.returncode}: {proc.stderr[-400:]}")
    model = precise.parse_output(proc.stdout, ec_g_cm3)
    model["axis_ratio"] = ratio
    return model


def solve_fixed_frequency(binary: Path, table: Path, ec: float,
                          previous_ratio: float | None) -> dict:
    """At one central density, bracket and solve the observed spin directly."""
    if previous_ratio is None:
        candidates = list(RATIOS)
    else:
        candidates = sorted(set([1.0, .90, .93, .95, .97, .99, .998,
                                 max(.90, previous_ratio - .012),
                                 max(.90, previous_ratio - .004),
                                 min(1.0, previous_ratio + .004),
                                 min(1.0, previous_ratio + .012)]), reverse=True)
    trace, evaluated = [], []
    for ratio in candidates:
        try:
            model = run_rns(binary, table, ec, ratio)
            delta = model["spin_hz"] - TARGET_HZ
            trace.append({"axis_ratio": ratio, "spin_hz": model["spin_hz"],
                          "delta_hz": delta, "status": "OK"})
            evaluated.append((ratio, delta, model))
        except Exception as exc:
            trace.append({"axis_ratio": ratio, "status": "FAILED",
                          "reason": type(exc).__name__ + ": " + str(exc)[:200]})
    evaluated.sort(key=lambda x: x[0])
    bracket = None
    for left, right in zip(evaluated, evaluated[1:]):
        if left[1] == 0 or left[1] * right[1] < 0:
            bracket = (left[0], right[0])
            break
    if bracket is None:
        raise ValueError("NO_FIXED_FREQUENCY_BRACKET; see trace")

    cache: dict[float, dict] = {x[0]: x[2] for x in evaluated}

    def residual(ratio: float) -> float:
        model = run_rns(binary, table, ec, ratio)
        cache[ratio] = model
        return model["spin_hz"] - TARGET_HZ

    ratio = float(brentq(residual, *bracket, xtol=2e-8, rtol=2e-10,
                         maxiter=50))
    model = cache.get(ratio) or run_rns(binary, table, ec, ratio)
    if abs(model["spin_hz"] - TARGET_HZ) > 1e-3:
        raise ValueError("FIXED_FREQUENCY_RESIDUAL_TOO_LARGE")
    return {"central_energy_density_g_cm3": ec,
            "central_density_e15": ec / 1e15,
            "mass_msun": model["mass_msun"],
            "radius_eq_km": model["radius_eq_km"],
            "spin_hz": model["spin_hz"], "axis_ratio": ratio,
            "trace": trace}


def make_density_grid() -> np.ndarray:
    # Dense around the measured mass and the first mass maximum; broad enough
    # to bracket both ends of the source radio-mass support.
    e15 = np.unique(np.r_[np.arange(.80, 1.30 + 1e-9, .05),
                          np.arange(1.30, 2.50 + 1e-9, .01),
                          np.arange(2.50, 3.31 + 1e-9, .025)])
    return e15 * 1e15


def stable_rising_branch(rows: list[dict]) -> list[dict]:
    good = sorted(rows, key=lambda x: x["central_energy_density_g_cm3"])
    if len(good) < 40:
        raise ValueError(f"too few direct fixed-frequency roots: {len(good)}")
    masses = np.array([x["mass_msun"] for x in good])
    peak = int(np.argmax(masses))
    if peak < 10 or peak >= len(good) - 2:
        raise ValueError("fixed-frequency first mass maximum is not bracketed")
    before = np.diff(masses[:peak + 1])
    if np.any(before < -2e-4):
        raise ValueError("mass is not monotone on the selected rising branch")
    branch = good[:peak + 1]
    by_mass = sorted(branch, key=lambda x: x["mass_msun"])
    m = np.array([x["mass_msun"] for x in by_mass])
    if np.any(np.diff(m) <= 0):
        raise ValueError("duplicate/nonmonotone gravitational masses")
    if m[0] > M_MIN + .005 or m[-1] < 2.10:
        raise ValueError(f"source mass support not bracketed: [{m[0]}, {m[-1]}]")
    return by_mass


def load_surface(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        m = np.asarray(z["mass_centres"], float)
        r = np.asarray(z["radius_centres_km"], float)
        like = np.asarray(z["relative_likelihood_L_over_Z"], float)
        support = np.asarray(z["hard_source_support"], bool)
    if m.shape != (401,) or r.shape != (581,) or like.shape != (401, 581):
        raise ValueError(f"unexpected F38 surface shapes in {path.name}")
    if np.any(~np.isfinite(like)) or np.any(like < 0) or np.any(like[~support] != 0):
        raise ValueError(f"invalid F38 likelihood/support in {path.name}")
    return m, r, like


def integrate_surfaces(branch: list[dict], f38_dir: Path) -> dict:
    masses = np.array([x["mass_msun"] for x in branch])
    radii = np.array([x["radius_eq_km"] for x in branch])
    radius_of_mass = PchipInterpolator(masses, radii, extrapolate=False)
    evidence: dict[str, dict] = {}
    for kind in ("weighted", "resampled"):
        for sm, sr in BANDWIDTHS:
            tag = f"{sm:.3f}_{sr:.2f}"
            path = f38_dir / f"posterior_prior_ratio_{kind}_{tag}.npz"
            if not path.is_file():
                raise FileNotFoundError(f"F38 artifact member missing: {path.name}")
            m, r, like = load_surface(path)
            l_at_curve = RegularGridInterpolator(
                (m, r), like, method="linear", bounds_error=False, fill_value=0.0
            )(np.column_stack((m, np.clip(radius_of_mass(m), r[0], r[-1]))))
            l_at_curve[(m < masses[0]) | (m > masses[-1])] = 0.0
            q = truncnorm.pdf(m, -5, 5, loc=M_MU, scale=M_SIG)
            value = float(np.trapezoid(q * l_at_curve, m))
            prior_coverage = float(np.trapezoid(q[(m >= masses[0]) & (m <= masses[-1])],
                                                  m[(m >= masses[0]) & (m <= masses[-1])]))
            evidence[f"{kind}_{tag}"] = {
                "integral_L_over_Z_qradio_dM": value,
                "radio_prior_mass_coverage_on_RNS_branch": prior_coverage,
                "integral_definition": "F38 approximate L/Z(M,R_eq(M,f)) times one normalized truncated radio-mass density; zero outside the causal-completion rising branch",
                "bandwidth_M_R": [sm, sr],
                "not_final_EOS_Bayes": True,
            }
    return evidence


def run(args) -> dict:
    npz, native_table = args.source_npz, args.native_table
    if causal.sha256(npz) != causal.NPZ_SHA or causal.sha256(native_table) != causal.LAL_TABLE_SHA:
        raise ValueError("pinned JESTER or native LALSuite EOS SHA mismatch")
    mavg = causal.validate_source(native_table, npz)
    eos = causal.NativeAPR4CausalEOS(native_table)
    table = args.work / "APR4_CAUSAL_7p26p4_200.rns"
    rows, conversion = causal.make_rows(eos, mavg, 200)
    causal.write_rns(table, rows)
    table_hash = sha256(table)
    results, failures, previous = [], [], None
    for ec in make_density_grid():
        try:
            item = solve_fixed_frequency(args.binary_fine, table, float(ec), previous)
            previous = item["axis_ratio"]
            results.append(item)
            print(json.dumps({"ec_e15": item["central_density_e15"],
                              "M": item["mass_msun"], "R_eq": item["radius_eq_km"],
                              "ratio": item["axis_ratio"]}), flush=True)
        except Exception as exc:
            failures.append({"central_energy_density_g_cm3": float(ec),
                             "reason": type(exc).__name__ + ": " + str(exc)[:300]})
    branch = stable_rising_branch(results)
    # Mesh check at three densities spanning low/mid/high likelihood support.
    mesh_checks = []
    for ec in (1.35e15, 1.7605e15, 2.15e15):
        fine = solve_fixed_frequency(args.binary_fine, table, ec, None)
        coarse = solve_fixed_frequency(args.binary_coarse, table, ec, fine["axis_ratio"])
        mesh_checks.append({"ec_g_cm3": ec, "fine": fine, "coarse": coarse,
                            "delta_M_msun": coarse["mass_msun"]-fine["mass_msun"],
                            "delta_R_km": coarse["radius_eq_km"]-fine["radius_eq_km"]})
    if max(abs(x["delta_R_km"]) for x in mesh_checks) > .02:
        raise ValueError("coarse/fine RNS mesh check exceeds 0.02 km")
    evidence = integrate_surfaces(branch, args.f38_dir)
    rec = {
        "schema": "j0740-causal-apr4-fixed-frequency-curve-f38-integral-v1",
        "status": "PASS_CONDITIONAL_APPROXIMATE_F38_CURVE_INTEGRAL",
        "model": causal.MODEL,
        "target_spin_hz": TARGET_HZ,
        "mass_prior": {"distribution": "truncated Gaussian on source F38 +/-5sigma support; applied once",
                       "mu_msun": M_MU, "sigma_msun": M_SIG,
                       "support_msun": [M_MIN, M_MAX]},
        "inputs": {"native_lal_table_sha256": causal.sha256(native_table),
                   "jester_npz_sha256": causal.sha256(npz),
                   "rns_table_sha256": table_hash,
                   "rns_commit": precise.RNS_COMMIT,
                   "F38_run_id": F38_RUN_ID,
                   "F38_artifact": F38_ARTIFACT},
        "conversion": conversion,
        "fixed_frequency_roots_success": len(results),
        "fixed_frequency_roots_failures": failures,
        "central_density_sweep": results,
        "rising_branch_mass_min_msun": branch[0]["mass_msun"],
        "rising_branch_mass_max_sampled_msun": branch[-1]["mass_msun"],
        "sampled_turning_point": results[max(range(len(results)),
                                        key=lambda i: results[i]["mass_msun"])],
        "fine_coarse_mesh_checks": mesh_checks,
        "conditional_evidence_diagnostics": evidence,
        "limitations": [
            "F38 is posterior/source-prior division from published marginalized samples with KDE bandwidth systematics, not a fresh compiled X-PSI photon likelihood.",
            "R_eq(M,f) is directly solved on the fine RNS mesh at a sampled central-density grid; interpolation is only for likelihood integration.",
            "Evidence is conditional on the stated truncated Gaussian mass prior and this single causal-completion EOS; it is not a seven-EOS posterior or final EOS Bayes factor.",
            "Fixed-frequency branch selection is not a global dynamical-stability proof; F37 sampled fixed-J turning evidence is separate.",
            "The source-native physical mu0/crust join remains conditional."
        ]
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rec, indent=2, sort_keys=True,
                                   allow_nan=False)+"\n", encoding="utf-8")
    csv = ["central_density_g_cm3,mass_msun,radius_eq_km,spin_hz,axis_ratio"]
    csv += [f"{x['central_energy_density_g_cm3']:.9g},{x['mass_msun']:.12g},"
            f"{x['radius_eq_km']:.12g},{x['spin_hz']:.12g},{x['axis_ratio']:.12g}"
            for x in branch]
    args.out.with_suffix(".csv").write_text("\n".join(csv)+"\n",encoding="utf-8")
    print(json.dumps({"status": rec["status"],
                      "roots": rec["fixed_frequency_roots_success"],
                      "branch_masses": [rec["rising_branch_mass_min_msun"],
                                        rec["rising_branch_mass_max_sampled_msun"]],
                      "evidence": evidence}, indent=2), flush=True)
    return rec


def selftest() -> None:
    q = truncnorm.pdf(np.linspace(M_MIN, M_MAX, 5000), -5, 5,
                      loc=M_MU, scale=M_SIG)
    x = np.linspace(M_MIN, M_MAX, 5000)
    assert abs(float(np.trapezoid(q, x))-1) < 1e-5
    assert len(make_density_grid()) > 100
    toy_m = np.linspace(1.7, 2.2, 80)
    toy_r = 12 - 0.5*(toy_m-1.7)
    interp = PchipInterpolator(toy_m, toy_r, extrapolate=False)
    assert abs(float(interp(2.0))-11.85) < 1e-10
    print("SELFTEST_PASS: radio-mass normalization, sweep coverage, curve interpolation")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--source-npz", type=Path)
    p.add_argument("--native-table", type=Path)
    p.add_argument("--binary-coarse", type=Path)
    p.add_argument("--binary-fine", type=Path)
    p.add_argument("--work", type=Path)
    p.add_argument("--f38-dir", type=Path)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    if a.selftest:
        selftest()
        return
    for name in ("source_npz", "native_table", "binary_coarse", "binary_fine",
                 "work", "f38_dir", "out"):
        if getattr(a, name) is None:
            p.error("--"+name.replace("_", "-")+" is required")
    a.work.mkdir(parents=True, exist_ok=True)
    run(a)


if __name__ == "__main__":
    main()

