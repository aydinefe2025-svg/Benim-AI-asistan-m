"""Summarize a retained two-grid RNS run artifact without rerunning RNS."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

EOS = ("APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")
TARGET_MASS = 2.073


def _branch_diagnostic(scan: dict, models_key: str, failures_key: str) -> dict:
    """Summarize target support on the saved successful central-density grid."""
    models = sorted(scan.get(models_key, []),
                    key=lambda row: row.get("central_energy_density_g_cm3", float("inf")))
    good = [row for row in models
            if isinstance(row.get("mass_msun"), (int, float))
            and isinstance(row.get("central_energy_density_g_cm3"), (int, float))]
    brackets = []
    first_turn = None
    for left, right in zip(good, good[1:]):
        if right["mass_msun"] < left["mass_msun"] - 0.002 and first_turn is None:
            first_turn = {"left_mass_msun": left["mass_msun"],
                          "right_mass_msun": right["mass_msun"],
                          "left_density_g_cm3": left["central_energy_density_g_cm3"],
                          "right_density_g_cm3": right["central_energy_density_g_cm3"]}
        if (first_turn is None and left["mass_msun"] < TARGET_MASS < right["mass_msun"]):
            brackets.append({"left_mass_msun": left["mass_msun"],
                             "right_mass_msun": right["mass_msun"],
                             "left_density_g_cm3": left["central_energy_density_g_cm3"],
                             "right_density_g_cm3": right["central_energy_density_g_cm3"]})
    below = [m for m in good if m["mass_msun"] <= TARGET_MASS]
    above = [m for m in good if m["mass_msun"] >= TARGET_MASS]
    peak = max(good, key=lambda row: row["mass_msun"]) if good else None
    return {
        "successful_points": len(good),
        "failed_points": len(scan.get(failures_key, [])),
        "target_mass_msun": TARGET_MASS,
        "stable_target_bracket_count": len(brackets),
        "stable_target_brackets": brackets,
        "nearest_below_target_mass_msun": max((m["mass_msun"] for m in below), default=None),
        "nearest_above_target_mass_msun": min((m["mass_msun"] for m in above), default=None),
        "sampled_peak_mass_msun": peak["mass_msun"] if peak else None,
        "sampled_peak_density_g_cm3": peak["central_energy_density_g_cm3"] if peak else None,
        "first_sampled_turnover": first_turn,
    }


def _find_report(root: Path, grid: str) -> Path:
    candidates = list(root.rglob("J0740_fixed_mass_spin.json"))
    found = [p for p in candidates if grid in str(p)]
    if len(found) != 1:
        raise ValueError(f"expected exactly one {grid} fixed-mass-spin report; found {len(found)}")
    return found[0]


def summarize(root: Path) -> dict:
    base_path = _find_report(root, "151x301")
    fine_path = _find_report(root, "201x401")
    base = json.loads(base_path.read_text(encoding="utf-8"))
    fine = json.loads(fine_path.read_text(encoding="utf-8"))
    rows = {}
    for name in EOS:
        a, b = base.get("eos", {}).get(name, {}), fine.get("eos", {}).get(name, {})
        row = {
            "base_status": a.get("status", "MISSING"),
            "fine_status": b.get("status", "MISSING"),
            "fine_reason": b.get("reason"),
            "fine_failed_stage": b.get("failed_stage"),
            "fine_error_type": b.get("error_type"),
        }
        if "scan" in b:
            scan = b["scan"]
            row["fine_scan"] = {
                "rotating_successes": len(scan.get("rotating_models", [])),
                "rotating_failures": len(scan.get("rotating_failures", [])),
                "static_successes": len(scan.get("nonrotating_models", [])),
                "static_failures": len(scan.get("nonrotating_failures", [])),
                "rotating_failure_examples": scan.get("rotating_failures", [])[:5],
                "rotating_target_support": _branch_diagnostic(
                    scan, "rotating_models", "rotating_failures"),
                "static_target_support": _branch_diagnostic(
                    scan, "nonrotating_models", "nonrotating_failures"),
            }
        root_fields = (
            ("rns_rotating_at_target", "mass_msun", "rotating_mass_msun"),
            ("rns_rotating_at_target", "radius_eq_km", "rotating_radius_eq_km"),
            ("rns_rotating_at_target", "central_energy_density_g_cm3", "rotating_central_energy_density_g_cm3"),
            ("rns_rotating_at_target", "spin_hz_reported", "spin_hz_reported"),
            ("rns_static_at_same_gravitational_mass", "radius_eq_km", "static_radius_eq_km"),
            ("rns_static_at_same_gravitational_mass", "mass_msun", "static_mass_msun"),
            ("rns_minus_jester_static_tov_km", None, "static_minus_source_tov_radius_km"),
        )
        for section, key, label in root_fields:
            av = a.get(section, {}).get(key) if key else a.get(section)
            bv = b.get(section, {}).get(key) if key else b.get(section)
            if av is not None:
                row[f"base_{label}"] = av
            if bv is not None:
                row[f"fine_{label}"] = bv
            if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
                row[f"delta_{label}"] = bv-av
        rows[name] = row
    return {
        "schema": "j0740-two-grid-root-run-summary-v1",
        "source_run": 42827242417,
        "target_mass_msun": TARGET_MASS,
        "base_report_status": base.get("status"),
        "base_validated_count": base.get("validated_eos_count"),
        "fine_report_status": fine.get("status"),
        "fine_validated_count": fine.get("validated_eos_count"),
        "base_report_path": str(base_path),
        "fine_report_path": str(fine_path),
        "models": rows,
        "limitations": [
            "This summarizes the preserved CI artifact; no RNS solver calls are repeated.",
            "A missing 201x401 target root is a failed numerical/branch gate, not silently dropped.",
            "All measured root deltas are finite-grid sensitivities, not a continuum extrapolation.",
            "No EOS posterior or Bayes factor is computed.",
        ],
        "EOS_Bayes": "NOT_RUN",
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = summarize(a.run_dir)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    for name, row in result["models"].items():
        print(name, row["base_status"], row["fine_status"],
              row.get("delta_rotating_radius_eq_km"), row.get("delta_spin_hz_reported"),
              row.get("fine_reason"), flush=True)
    print(json.dumps({"base": result["base_report_status"], "fine": result["fine_report_status"],
                      "validated": result["fine_validated_count"], "required": 7,
                      "EOS_Bayes": "NOT_RUN"}), flush=True)


if __name__ == "__main__":
    main()

