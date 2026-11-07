"""Seven source-matched, uniformly rotating full-GR EOS sequences for J0740.

Independent RNS solution at the observed spin, with fixed gravitational-mass
static comparisons. No event-level NICER likelihood or Bayesian EOS evidence.
The 12.9-GB NICER archive is intentionally not accessed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from jester_to_rns import from_jester_npz, write_rns
from rns_benchmark import OBSERVED_SPIN_HZ, RNS_COMMIT, run_rns, sha256_file
from target_mass_rns import TARGET_MASS_MSUN, fixed_gravitational_mass_radius_difference
from resilient_mass_root import resilient_mass_root, NumericalRootError


EOS_NAMES = ("APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")
JESTER_COMMIT = "e6768650ce992abfd1153a6833857572fe5cd230"


def stable_source_radius_at_mass(source: Path, mass: float) -> tuple[float, dict]:
    """Use only the ascending *first* TOV stable branch, never its turnback.

    A JESTER input may include an unstable extension after maximum mass.
    Never sort mass-radius pairs, extrapolate, or silently smooth upstream
    non-monotonic points within the pre-turning stable branch.
    """
    with np.load(source, allow_pickle=False) as data:
        masses = np.asarray(data["masses_EOS"], dtype=float)
        radii = np.asarray(data["radii_EOS"], dtype=float)
    if (masses.ndim != 1 or radii.shape != masses.shape or len(masses) < 10
            or not np.all(np.isfinite(masses)) or not np.all(np.isfinite(radii))
            or np.any(masses <= 0) or np.any(radii <= 0)):
        raise ValueError("JESTER TOV reference M/R arrays invalid")
    peak = int(np.argmax(masses))
    stable_m = masses[:peak + 1]
    stable_r = radii[:peak + 1]
    if len(stable_m) < 10 or np.any(np.diff(stable_m) <= 0):
        raise ValueError("Source TOV has nonmonotone mass before first stable maximum; reject")
    if not (stable_m[0] <= mass <= stable_m[-1]):
        raise ValueError("Target mass outside source TOV ascending stable branch")
    return float(np.interp(mass, stable_m, stable_r)), {
        "total_source_nodes": int(len(masses)),
        "first_maximum_index": peak,
        "first_maximum_mass_msun": float(stable_m[-1]),
        "stable_branch_nodes": int(len(stable_m)),
        "discarded_post_maximum_nodes": int(len(masses) - len(stable_m)),
        "selection": "ascending original sequence through first global mass maximum; never sort",
    }


def first_stable_crossing(models: list[dict], target: float) -> tuple[float, float] | None:
    """Bracket the FIRST increasing-mass crossing, never the unstable branch."""
    if not (math.isfinite(target) and target > 0):
        raise ValueError("invalid target")
    ordered = sorted(models, key=lambda x: x["central_energy_density_g_cm3"])
    previous = None
    for model in ordered:
        ec = float(model["central_energy_density_g_cm3"])
        mass = float(model["mass_msun"])
        if not (math.isfinite(ec) and math.isfinite(mass) and ec > 0 and mass > 0):
            raise ValueError("invalid scanned stellar model")
        if previous is not None:
            if ec <= previous["central_energy_density_g_cm3"]:
                raise ValueError("duplicate central density in scan")
            if mass < previous["mass_msun"] - 0.002:
                break  # maximum stable mass reached; DO NOT search beyond it
            if previous["mass_msun"] < target < mass:
                return (float(previous["central_energy_density_g_cm3"]), ec)
        previous = model
    return None


def density_scan(binary: Path, table: Path, spin_hz: float,
                 density_grid: np.ndarray) -> tuple[list[dict], list[dict]]:
    successes, failures = [], []
    for ec in density_grid:
        try:
            model = run_rns(binary, table, central_density=float(ec), spin_hz=spin_hz,
                            spin_tolerance_hz=0.25 if spin_hz else 0.10)
            # Store concise measurement data; full RNS stdout is not needed at every scan point.
            successes.append({k: v for k, v in model.items() if k != "raw_stdout_tail"})
        except (RuntimeError, ValueError, TimeoutError) as exc:
            failures.append({"central_energy_density_g_cm3": float(ec),
                             "error_type": type(exc).__name__,
                             "reason": str(exc)[:500]})
    return successes, failures


def solve_eos(binary: Path, source: Path, result_dir: Path,
              *, target_mass: float = TARGET_MASS_MSUN, scan_points: int = 18) -> dict:
    name = source.stem
    if name not in EOS_NAMES:
        raise ValueError(f"unrecognized source EOS: {name}")
    if not (source.is_file() and binary.is_file()):
        raise FileNotFoundError(f"missing RNS binary or JESTER EOS {name}")
    rows, conversion = from_jester_npz(source)
    table = result_dir / f"eos{name}_from_JESTER_196pt"
    write_rns(table, rows)
    max_eos_density = float(rows[-1, 0])
    maximum = min(2.5e15, max_eos_density * 0.95)
    minimum = 4.0e14
    if maximum <= minimum:
        raise ValueError("EOS central density range does not permit numerical scan")
    densities = np.geomspace(minimum, maximum, scan_points)

    rotations, rejected_rotations = density_scan(binary, table, OBSERVED_SPIN_HZ, densities)
    statics, rejected_statics = density_scan(binary, table, 0., densities)
    result = {
        "eos": name,
        "jester_source_commit": JESTER_COMMIT,
        "source_npz_sha256": conversion["source_npz_sha256"],
        "rns_table_sha256": sha256_file(table),
        "conversion": conversion,
        "scan": {"spin_hz": OBSERVED_SPIN_HZ,
                 "central_density_grid_g_cm3": [float(x) for x in densities],
                 "rotating_models": rotations, "nonrotating_models": statics,
                 "rotating_failures": rejected_rotations, "nonrotating_failures": rejected_statics},
    }
    rot_bracket = first_stable_crossing(rotations, target_mass)
    static_bracket = first_stable_crossing(statics, target_mass)
    # Some upstream RNS density points do not converge. A gap in the
    # rotating grid must not be misreported as a physical EOS exclusion.
    # Search independently near the source-matched static target crossing;
    # each failed trial remains in the machine-readable evidence.
    if rot_bracket is None and static_bracket is not None:
        rescue_grid = np.linspace(max(minimum, 0.85 * static_bracket[0]),
                                  min(maximum, 1.2 * static_bracket[1]), 24)
        rescue_models, rescue_failed = density_scan(
            binary, table, OBSERVED_SPIN_HZ, rescue_grid)
        rotations = sorted(rotations + rescue_models,
                           key=lambda m: m["central_energy_density_g_cm3"])
        rejected_rotations.extend(rescue_failed)
        result["scan"]["rotating_models"] = rotations
        result["scan"]["rotating_failures"] = rejected_rotations
        result["scan"]["additional_targeted_rotating_grid_g_cm3"] = [
            float(x) for x in rescue_grid]
        rot_bracket = first_stable_crossing(rotations, target_mass)
    if rot_bracket is None or static_bracket is None:
        result["status"] = "NO_VALIDATED_STABLE_CROSSING"
        result["reason"] = "Target gravitational mass not bracketed on both sampled stable branches"
        result["brackets"] = {"rotating": rot_bracket, "static": static_bracket}
        return result

    try:
        root_stage = "rotating"
        rotating, rot_trace = resilient_mass_root(
            lambda ec: run_rns(binary, table, central_density=ec,
                               spin_hz=OBSERVED_SPIN_HZ, spin_tolerance_hz=0.25),
            target_mass, *rot_bracket)
        root_stage = "static"
        static, static_trace = resilient_mass_root(
            lambda ec: run_rns(binary, table, central_density=ec, spin_hz=0.),
            target_mass, *static_bracket)
        radius_delta = fixed_gravitational_mass_radius_difference(
            rotating, static, target_mass)
        root_stage = "source_TOV"
        ref_radius, source_stable_branch = stable_source_radius_at_mass(
            source, static["mass_msun"])
        error_km = static["radius_eq_km"] - ref_radius
    except (RuntimeError, ValueError, NumericalRootError) as exc:
        result["status"] = "NUMERICAL_ROOT_OR_TOV_VALIDATION_FAILED"
        result["reason"] = str(exc)[:900]
        result["error_type"] = type(exc).__name__
        result["failed_stage"] = locals().get("root_stage", "unknown")
        if isinstance(exc, NumericalRootError):
            result["failed_root_trace"] = exc.trace
        result["brackets"] = {"rotating": rot_bracket, "static": static_bracket}
        return result
    result.update({
        "rns_rotating_at_target": rotating,
        "rns_static_at_same_gravitational_mass": static,
        "delta_radius_at_same_gravitational_mass_km": radius_delta,
        "jester_static_tov_radius_km": ref_radius,
        "jester_reference_stable_branch_selection": source_stable_branch,
        "rns_minus_jester_static_tov_km": error_km,
        "rotating_bisection_trace": rot_trace,
        "static_bisection_trace": static_trace,
        "target_mass_msun": target_mass,
        "target_mass_tolerance_msun": 0.0015,
        "rotating_spin_numerical_residual_limit_hz": 0.25,
        "static_tov_radius_tolerance_km": 0.25,
    })
    if abs(error_km) > 0.25:
        result["status"] = "FAILED_INDEPENDENT_STATIC_TOV_VALIDATION"
        return result
    result["status"] = "MATCHED_FIXED_MASS_RNS_GR_AND_STATIC_TOV_VALIDATED"
    return result


def compute_all(binary: Path, source_dir: Path, result_dir: Path,
                target_mass: float = TARGET_MASS_MSUN, scan_points: int = 18) -> dict:
    if not 8 <= scan_points <= 40:
        raise ValueError("scan_points must be 8 to 40")
    result_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for name in EOS_NAMES:
        try:
            results[name] = solve_eos(
                binary, source_dir / f"{name}.npz", result_dir,
                target_mass=target_mass, scan_points=scan_points)
        except Exception as exc:
            # Report a failed EOS explicitly; never silently substitute another EOS.
            results[name] = {"eos": name, "status": "FAILED_NOT_VALIDATED",
                             "error_type": type(exc).__name__,
                             "reason": str(exc)[:1000]}
        print(name, results[name]["status"], flush=True)
    count = sum(r["status"] == "MATCHED_FIXED_MASS_RNS_GR_AND_STATIC_TOV_VALIDATED"
                for r in results.values())
    return {
        "schema": "j0740-seven-eos-fixed-spin-rns-v1",
        "status": "ALL_SEVEN_VALIDATED" if count == 7 else "PARTIAL_NOT_FINAL",
        "validated_eos_count": count, "required_eos_count": len(EOS_NAMES),
        "rns_upstream_commit": RNS_COMMIT,
        "rns_executable_sha256": sha256_file(binary),
        "jester_upstream_commit": JESTER_COMMIT,
        "spin_hz": OBSERVED_SPIN_HZ,
        "rotating_spin_numerical_residual_limit_hz": 0.25,
        "target_gravitational_mass_msun": target_mass,
        "limitations": [
            "Discrete seven-EOS test only, not a continuous EOS posterior",
            "Source-matched RNS fixed-frequency sequences, not X-PSI waveform likelihood",
            "No EOS model Bayes factors or prior-marginalized NICER/XMM likelihood",
            "RNS numerical stdout mass and radius precision is limited",
            "Static TOV source comparison is required separately for every EOS",
            "No same-baryonic-mass evolutionary spin-up claim",
        ],
        "eos": results,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rns", type=Path, required=True)
    p.add_argument("--jester-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--mass", type=float, default=TARGET_MASS_MSUN)
    p.add_argument("--scan-points", type=int, default=18)
    a = p.parse_args()
    if not (math.isfinite(a.mass) and 0.5 < a.mass < 3.5):
        p.error("target mass outside valid bounds")
    report = compute_all(a.rns, a.jester_dir, a.out.parent,
                         a.mass, a.scan_points)
    a.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "validated": report["validated_eos_count"],
                      "required": report["required_eos_count"]}))
    if report["validated_eos_count"] != len(EOS_NAMES):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
