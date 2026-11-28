"""Compare fixed-M/fixed-spin RNS roots at two spacetime resolutions.

This is a numerical convergence screen for the same pinned source EOS files.
It retains per-model failures and never converts a failed root into an EOS
exclusion or a posterior result.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


EOS = ("APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")
BASE_GRID = "151x301"
FINE_GRID = "201x401"
MASS_TOL_MSUN = 0.0015
RADIUS_TOL_KM = 0.15
SPIN_DELTA_TOL_HZ = 0.25


def _number(obj: dict, key: str) -> float:
    value = float(obj[key])
    if not math.isfinite(value):
        raise ValueError(f"nonfinite {key}")
    return value


def _root_row(report: dict, name: str, grid: str) -> dict:
    row = report["eos"][name]
    if row.get("status") != "MATCHED_FIXED_MASS_RNS_GR_AND_STATIC_TOV_VALIDATED":
        raise ValueError(f"{name} {grid}: root/source TOV status is {row.get('status')!r}")
    rot = row["rns_rotating_at_target"]
    sta = row["rns_static_at_same_gravitational_mass"]
    if grid not in rot.get("raw_stdout_tail", "") or grid not in sta.get("raw_stdout_tail", ""):
        raise ValueError(f"{name} {grid}: compiled grid identity missing from solver output")
    mass = _number(rot, "mass_msun")
    target = _number(report, "target_gravitational_mass_msun")
    if abs(mass-target) > MASS_TOL_MSUN:
        raise ValueError(f"{name} {grid}: rotating mass root outside declared tolerance")
    spin = _number(rot, "spin_hz_reported")
    requested = _number(report, "spin_hz")
    spin_residual = spin-requested
    if abs(spin_residual) > _number(report, "rotating_spin_numerical_residual_limit_hz"):
        raise ValueError(f"{name} {grid}: spin residual outside declared limit")
    return {
        "source_npz_sha256": row["source_npz_sha256"],
        "mass_msun": mass,
        "rotating_radius_eq_km": _number(rot, "radius_eq_km"),
        "rotating_central_energy_density_g_cm3": _number(rot, "central_energy_density_g_cm3"),
        "spin_hz_reported": spin,
        "spin_residual_hz": spin_residual,
        "static_mass_msun": _number(sta, "mass_msun"),
        "static_radius_eq_km": _number(sta, "radius_eq_km"),
        "static_central_energy_density_g_cm3": _number(sta, "central_energy_density_g_cm3"),
    }


def compare(base: dict, fine: dict) -> dict:
    for label, report in ((BASE_GRID, base), (FINE_GRID, fine)):
        if (report.get("status") != "ALL_SEVEN_VALIDATED"
                or report.get("validated_eos_count") != len(EOS)
                or report.get("required_eos_count") != len(EOS)):
            raise ValueError(f"{label}: complete seven-EOS fixed-mass roots required")
        if report.get("rns_upstream_commit") != fine.get("rns_upstream_commit"):
            raise ValueError("RNS source commit differs between grids")
        if report.get("jester_upstream_commit") != fine.get("jester_upstream_commit"):
            raise ValueError("JESTER source commit differs between grids")
        if not math.isclose(_number(report, "target_gravitational_mass_msun"), 2.073,
                            rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("unexpected target mass")
        if not math.isclose(_number(report, "spin_hz"), 346.536369,
                            rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("unexpected target spin")
    models = {}
    failures = []
    for name in EOS:
        try:
            a = _root_row(base, name, BASE_GRID)
            b = _root_row(fine, name, FINE_GRID)
            if a["source_npz_sha256"] != b["source_npz_sha256"]:
                raise ValueError("source EOS hash differs between grids")
            delta_mass = b["mass_msun"] - a["mass_msun"]
            delta_rrot = b["rotating_radius_eq_km"] - a["rotating_radius_eq_km"]
            delta_rstatic = b["static_radius_eq_km"] - a["static_radius_eq_km"]
            delta_spin = b["spin_hz_reported"] - a["spin_hz_reported"]
            gates = {
                "mass_root_delta_pass": abs(delta_mass) <= MASS_TOL_MSUN,
                "rotating_radius_delta_pass": abs(delta_rrot) <= RADIUS_TOL_KM,
                "static_radius_delta_pass": abs(delta_rstatic) <= RADIUS_TOL_KM,
                "spin_delta_pass": abs(delta_spin) <= SPIN_DELTA_TOL_HZ,
            }
            models[name] = {
                "base": a, "fine": b,
                "delta_mass_msun": delta_mass,
                "delta_rotating_radius_eq_km": delta_rrot,
                "delta_static_radius_km": delta_rstatic,
                "delta_spin_hz": delta_spin,
                "gates": gates,
                "pass": all(gates.values()),
            }
            if not models[name]["pass"]:
                failures.append({"eos": name, "reason": "one or more prespecified mesh-delta gates failed",
                                 "gates": gates})
        except (KeyError, TypeError, ValueError) as exc:
            failures.append({"eos": name, "reason": str(exc)})
    return {
        "schema": "j0740-fixed-mass-spin-two-grid-root-convergence-v1",
        "status": "PASS" if len(models) == len(EOS) and not failures else "FAIL",
        "target_mass_msun": 2.073,
        "target_spin_hz": 346.536369,
        "grids": {"base": BASE_GRID, "fine": FINE_GRID},
        "tolerances": {"mass_delta_msun": MASS_TOL_MSUN,
                       "radius_delta_km": RADIUS_TOL_KM,
                       "spin_delta_hz": SPIN_DELTA_TOL_HZ},
        "models": models,
        "failures": failures,
        "limitations": [
            "Two finite grids are a mesh-sensitivity check, not a continuum extrapolation.",
            "Passing numerical roots do not repair original EOS causality or monotonicity violations.",
            "Sparse central-density tracks do not establish continuous turning points or maximum mass.",
            "No NICER/XMM likelihood or EOS Bayes evidence is evaluated.",
        ],
        "EOS_Bayes": "NOT_RUN",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--fine", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = compare(json.loads(args.base.read_text(encoding="utf-8")),
                     json.loads(args.fine.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "models": len(result["models"]),
                      "failures": result["failures"]}))
    if result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

