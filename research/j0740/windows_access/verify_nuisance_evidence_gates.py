"""Fail-closed, dependency-free acceptance audit of *public summary* nuisance evidence.

This is NOT an independent X-PSI photon/NPZ verification. It checks recorded
metrics against predeclared thresholds and guards against unpaired K4/K8 claims.
The raw-sample checker verify_tailcorr_heldout.py has a separate purpose.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parents[1] / (
    "nuisance_proposal_regression_and_k4_comparison_2026-11-11.json"
)
# These are the predeclared gates, not learned from a candidate's outcome.
GATES = {
    "ESS_per_run_min": 100.0,
    "max_weight_fraction_max": 0.05,
    "phase_ESS_each_min": 30.0,
    "between_run_log_integral_spread_max": 0.20,
    "256_to_512_log_integral_drift_max": 0.10,
}


class EvidenceError(ValueError):
    """Evidence is incomplete, contradictory, or unsafe to certify."""


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{name}: expected finite number")
    value = float(value)
    if not math.isfinite(value):
        raise EvidenceError(f"{name}: non-finite number")
    return value


def point(value, name):
    if not isinstance(value, list) or len(value) != 2:
        raise EvidenceError(f"{name}: expected [mass, radius]")
    result = tuple(finite(v, name) for v in value)
    if result[0] <= 0 or result[1] <= 0:
        raise EvidenceError(f"{name}: invalid mass/radius")
    return result


def four(values, name):
    if not isinstance(values, list) or len(values) != 4:
        raise EvidenceError(f"{name}: expected four independent runs")
    return [finite(v, name) for v in values]


def seeds(record, name, training=None):
    values = record["seeds"]
    if not isinstance(values, list) or len(values) != 4 or len(set(values)) != 4:
        raise EvidenceError(f"{name}: four distinct seeds required")
    if any(isinstance(s, bool) or not isinstance(s, int) for s in values):
        raise EvidenceError(f"{name}: seed must be integer")
    if training is not None and set(values) & set(training):
        raise EvidenceError(f"{name}: training/test seed overlap")
    return values


def score(record, name, target, training, training_seeds, expected_status=None):
    if point(list(target), f"{name}.target") == point(list(training), f"{name}.training"):
        raise EvidenceError(f"{name}: held-out target equals training point")
    used_seeds = seeds(record, name, training_seeds)
    ess = four(record["ESS"], f"{name}.ESS")
    weights = four(record["max_weight"], f"{name}.max_weight")
    phase = finite(record["minimum_phase_ESS"], f"{name}.phase_ESS")
    spread = finite(record["logI_spread"], f"{name}.logI_spread")
    drift = finite(record["max_256_to_512_drift"], f"{name}.drift")
    if min(ess) <= 0 or min(weights) <= 0 or max(weights) > 1 or phase < 0 or spread < 0 or drift < 0:
        raise EvidenceError(f"{name}: invalid importance metrics")
    checks = {
        "ESS": min(ess) >= GATES["ESS_per_run_min"],
        "max_weight": max(weights) <= GATES["max_weight_fraction_max"],
        "phase_ESS": phase >= GATES["phase_ESS_each_min"],
        "logI_spread": spread <= GATES["between_run_log_integral_spread_max"],
        "budget_drift": drift <= GATES["256_to_512_log_integral_drift_max"],
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    if record["status"] != status or (expected_status and status != expected_status):
        raise EvidenceError(f"{name}: recorded {record['status']!r} disagrees with recomputed {status}")
    return {
        "name": name,
        "training_point": list(training),
        "heldout_point": list(target),
        "test_seeds": used_seeds,
        "status": status,
        "gates": checks,
        "ESS_min": min(ess),
        "max_weight_max": max(weights),
        "phase_ESS_min": phase,
        "logI_spread": spread,
        "budget_drift_max": drift,
    }


def verify_report(doc):
    if not isinstance(doc, dict) or doc.get("EOS_Bayes") != "NOT_RUN":
        raise EvidenceError("Final EOS Bayes must remain NOT_RUN")
    shared = doc["k4_experiments_are_distinct"]["shared_physics"]
    sha = shared["native_model_manifest_sha256"]
    if not isinstance(sha, str) or re.fullmatch(r"[0-9a-fA-F]{64}", sha) is None:
        raise EvidenceError("Missing/invalid source model SHA-256")
    if shared["source_prior_or_likelihood_changed"] or shared["importance_weights_clipped_or_samples_deleted"]:
        raise EvidenceError("Source likelihood/prior or original importance samples modified")
    method = doc["new_method"]
    if method["no_pruning_or_clipping"] is not True or method["EOS_Bayes"] != "NOT_RUN":
        raise EvidenceError("Unsafe nuisance modification/finalization")
    if method["draws_per_seed"] != 512:
        raise EvidenceError("Expected preserved 512-draw experiments")
    for k, limit in GATES.items():
        if finite(method["thresholds_unchanged"][k], k) != limit:
            raise EvidenceError(f"{k}: predeclared threshold was changed")
    old = doc["k2_15_26_ess_correction"]
    vals = [finite(v, "historic K2 ESS") for v in old["ess_by_seed"].values()]
    if len(vals) != 4 or len(old["ess_by_seed"]) != 4:
        raise EvidenceError("Incomplete historic K2 evidence")
    if [min(vals), max(vals)] != [finite(v, "historic K2 range") for v in old["range"]]:
        raise EvidenceError("Historic K2 ESS range disagrees with individual seeds")
    if finite(old["minimum"], "historic K2 minimum") != min(vals):
        raise EvidenceError("Historic K2 minimum is inconsistent")
    if old["rerun"] is not False:
        raise EvidenceError("Historic K2 is not marked as preserved")

    v1 = doc["v1_heldout_results"]
    train1 = point(method["training_point_msun_km"], "v1.training")
    train_seeds1 = method["training_seeds"]
    declared_points = [point(p, "v1.heldout") for p in method["heldout_points_msun_km"]]
    target1, target2 = (2.073, 13.25), (2.000, 14.00)
    if declared_points != [target1, target2]:
        raise EvidenceError("v1 named held-out points mismatch source metadata")
    results = [
        score(v1["point_2_073_13_25"], "K4_v1_2.073_13.25", target1, train1, train_seeds1),
        score(v1["point_2_000_14_00"], "K4_v1_2.000_14.00", target2, train1, train_seeds1),
    ]

    v2 = doc["v2_heldout_results"]
    train2 = point(v2["training_point_msun_km"], "v2.training")
    target3 = point(v2["heldout_point_msun_km"], "v2.heldout")
    results.append(score(v2, "K4_v2_2.000_13.50", target3, train2, v2["training_seeds"]))
    v3 = doc["v3_heldout_results"]
    train3 = point(v3["training_point_msun_km"], "v3.training")
    target4 = point(v3["heldout_point_msun_km"], "v3.heldout")
    results.append(score(v3, "K8_v3_2.000_13.75", target4, train3, v3["training_seeds"]))
    if v3["model_sha256"].lower() != sha.lower():
        raise EvidenceError("K8 target model hash differs from shared model")
    if not isinstance(v3["proposal_identity_sha256"], str) or re.fullmatch(
        r"[0-9a-fA-F]{64}", v3["proposal_identity_sha256"]
    ) is None:
        raise EvidenceError("K8 fitted-proposal identity missing")
    if v3.get("gates") != "PASS_ALL" or v3.get("independent_recompute") != "PASS":
        raise EvidenceError("K8 saved independent check/gate label inconsistent")
    if results[2]["status"] != "FAIL" or results[3]["status"] != "PASS":
        raise EvidenceError("Unexpected K4/K8 reference status")

    # Equal training points do not make experiments paired if held-out targets differ.
    paired = "NOT_ESTABLISHED"
    reason = "different held-out M,R points"
    if train2 == train3 and target3 == target4:
        reason = "same target, but matching seeds/protocol and controlled K comparison not certified"
    elif train2 != train3:
        reason = "training and/or held-out points differ"
    if doc["EOS_Bayes"] != "NOT_RUN":
        raise EvidenceError("Invalid final EOS status")
    return {
        "public_summary_arithmetic": "PASS",
        "private_photon_npz_independent_check": "NOT_PERFORMED",
        "predeclared_gates": GATES,
        "points": results,
        "k4_k8_paired_superiority": paired,
        "paired_limitation": reason,
        "full_MR_domain_convergence": "NOT_ESTABLISHED",
        "EOS_Bayes": "NOT_RUN",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?", type=Path, default=EVIDENCE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        output = verify_report(json.loads(args.evidence.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL_CLOSED: {exc}", file=sys.stderr)
        return 2
    result = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
