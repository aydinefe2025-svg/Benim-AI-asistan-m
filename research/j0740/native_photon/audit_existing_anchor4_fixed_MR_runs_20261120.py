"""Independent audit of four already-completed 512-draw fixed-M/R runs.

No photon likelihood is evaluated here.  The script reloads frozen run
summaries, samples, and per-draw receipts, and independently recalculates the
predeclared ESS/weight/phase/log-integral gates.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import logsumexp


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "evidence" / "native_photon"
OUT = Path(__file__).with_name("J0740_ANCHOR4_FIXED_MR_EXISTING_RUNS_AUDIT_20261120.json")
SEEDS = (111501, 111503, 111507, 111511)
EXPECTED_POINT = (2.2, 12.53)
EXPECTED_MODEL = "fbf6d7969072d96aeed1f883cd0b5fae726754355fea6c5593c2e329a4fe1fbb"
THRESHOLDS = {
    "min_ESS_100": 100.0,
    "max_weight_fraction_005": 0.05,
    "min_each_phase_ESS_30": 30.0,
    "max_independent_log_integral_spread_02": 0.2,
    "max_256_to_512_prefix_drift_01": 0.1,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def summarize(lw: np.ndarray, z: np.ndarray) -> dict:
    total = logsumexp(lw)
    normalized = np.exp(lw - total)
    phases = []
    for positive in (False, True):
        mask = (z[:, 2] > 0) == positive
        selected = lw[mask]
        part = logsumexp(selected)
        phases.append({
            "phase_positive": positive,
            "draws": int(mask.sum()),
            "posterior_weight_fraction": float(np.exp(part - total)),
            "ESS": float(np.exp(2.0 * part - logsumexp(2.0 * selected))),
        })
    return {
        "log_conditional_integral": float(total - math.log(len(lw))),
        "ESS": float(1.0 / np.dot(normalized, normalized)),
        "max_weight_fraction": float(normalized.max()),
        "phase_partitions": phases,
    }


def main() -> None:
    rows = []
    for seed in SEEDS:
        stem = f"MR_anchor_4_seed_{seed}"
        summary_path = EVIDENCE / f"{stem}_512.json"
        sample_path = EVIDENCE / f"{stem}_512_local.npz"
        eval_path = EVIDENCE / f"{stem}_evals_local.jsonl"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        samples = np.load(sample_path)
        z = samples["z"]
        lw = samples["logweights"]
        assert z.shape == (512, 13) and lw.shape == (512,)
        assert summary["status"] == "FROZEN_TRANSPORT_RADIAL_ANCHOR_NATIVE_RUN"
        assert tuple(summary["mass_radius"]) == EXPECTED_POINT
        assert summary["seed"] == seed and summary["draws"] == 512
        assert summary["frozen_model_sha256"] == EXPECTED_MODEL
        assert summary["nuisance_dimensions"] == 13
        assert summary["mass_radius_prior_factor_in_weight"] is False
        assert summary["weights_clipped"] is False

        eval_rows = [json.loads(line) for line in eval_path.read_text(encoding="utf-8").splitlines()]
        assert len(eval_rows) == 512
        assert [item["index"] for item in eval_rows] == list(range(512))
        assert all(item["model_sha256"] == EXPECTED_MODEL for item in eval_rows)
        assert all(tuple(item["fixed_mass_radius"]) == EXPECTED_POINT for item in eval_rows)
        assert np.max(np.abs(np.asarray([item["z"] for item in eval_rows]) - z)) < 1e-12

        independent = summarize(lw, z)
        recorded = summary["diagnostics"]
        assert abs(independent["log_conditional_integral"] - recorded["log_conditional_integral"]) < 2e-10
        assert abs(independent["ESS"] - recorded["ESS"]) < 1e-9
        assert abs(independent["max_weight_fraction"] - recorded["max_weight_fraction"]) < 1e-12
        for lhs, rhs in zip(independent["phase_partitions"], recorded["phase_partitions"]):
            assert lhs["draws"] == rhs["draws"]
            assert abs(lhs["ESS"] - rhs["ESS"]) < 1e-9
            assert abs(lhs["posterior_weight_fraction"] - rhs["posterior_weight_fraction"]) < 1e-11

        prefix = summary["prefixes"]
        assert [row["draws"] for row in prefix] == [64, 128, 256, 512]
        prefix_drift = abs(prefix[-1]["log_conditional_integral"] - prefix[-2]["log_conditional_integral"])
        rows.append({
            "seed": seed,
            "independent_diagnostics": independent,
            "prefix_256_to_512_log_integral_drift": prefix_drift,
            "input_files": [
                {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
                for path in (summary_path, sample_path, eval_path)
            ],
            "per_draw_receipt_count": len(eval_rows),
        })

    spread = max(row["independent_diagnostics"]["log_conditional_integral"] for row in rows) - min(
        row["independent_diagnostics"]["log_conditional_integral"] for row in rows
    )
    min_ess = min(row["independent_diagnostics"]["ESS"] for row in rows)
    max_weight = max(row["independent_diagnostics"]["max_weight_fraction"] for row in rows)
    min_phase_ess = min(
        phase["ESS"]
        for row in rows
        for phase in row["independent_diagnostics"]["phase_partitions"]
    )
    max_drift = max(row["prefix_256_to_512_log_integral_drift"] for row in rows)
    gates = {
        "min_ESS_100": min_ess >= THRESHOLDS["min_ESS_100"],
        "max_weight_fraction_005": max_weight <= THRESHOLDS["max_weight_fraction_005"],
        "min_each_phase_ESS_30": min_phase_ess >= THRESHOLDS["min_each_phase_ESS_30"],
        "max_independent_log_integral_spread_02": spread <= THRESHOLDS["max_independent_log_integral_spread_02"],
        "max_256_to_512_prefix_drift_01": max_drift <= THRESHOLDS["max_256_to_512_prefix_drift_01"],
    }
    report = {
        "schema": "j0740-existing-fixed-mr-four-seed-independent-audit-v1",
        "status": "PASS_FIXED_MR_NUMERICAL_GATES_ONLY" if all(gates.values()) else "FAIL_FIXED_MR_NUMERICAL_GATES",
        "point_mass_msun_radius_km": list(EXPECTED_POINT),
        "draws_per_run": 512,
        "independent_seeds": list(SEEDS),
        "frozen_proposal_sha256": EXPECTED_MODEL,
        "method": "Independent recomputation from saved logweights/z arrays; no likelihood calls, no weight clipping, same predeclared gate thresholds.",
        "thresholds": THRESHOLDS,
        "aggregate": {
            "minimum_run_ESS": min_ess,
            "maximum_single_weight_fraction": max_weight,
            "minimum_phase_ESS": min_phase_ess,
            "independent_log_integral_spread": spread,
            "maximum_256_to_512_prefix_drift": max_drift,
        },
        "gate_results": gates,
        "runs": rows,
        "scope_limitations": [
            "This is one fixed (M,R) point and does not establish convergence over the full M,R support.",
            "The conditional nuisance integral excludes the M,R prior factor by design.",
            "It is not an EOS curve integral, EOS evidence, or EOS posterior.",
        ],
        "EOS_Bayes": "NOT_RUN",
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "aggregate": report["aggregate"], "gate_results": gates}, indent=2))
    if not all(gates.values()):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
