"""Exact finite-sample tests for 2026 impact-cell one-week survival cohorts.

The input is the already audited *published subgroup counts*, NOT raw cells:
Sherman & Bombik, Batteries 12(6), 217, doi:10.3390/batteries12060217,
Methods 2.1-2.2 and Results 3.2.
All denominators are independent physical cells. No per-cycle pseudoreplication.
This is not a capacity/aging model and not proof of a causal SOC optimum.
"""
from __future__ import annotations

import argparse
import json
from itertools import combinations
from math import comb, prod
from pathlib import Path

from impact_2026_survival_audit import (
    DOI,
    IMPACT_ENERGIES,
    PER_STRATUM,
    SOC_PERCENT,
    SURVIVORS,
    wilson,
)


def fisher_two_sided(k1: int, n1: int, k2: int, n2: int) -> float:
    """Probability-ordered, fixed-marginal, exact two-sided 2x2 test."""
    for k, n in ((k1, n1), (k2, n2)):
        if not (isinstance(k, int) and isinstance(n, int) and 0 <= k <= n and n > 0):
            raise ValueError("invalid count or total")
    total = k1 + k2
    denominator = comb(n1 + n2, total)
    numerator_observed = comb(n1, k1) * comb(n2, k2)
    xmin, xmax = max(0, total - n2), min(n1, total)
    p_numerator = sum(
        comb(n1, x) * comb(n2, total - x)
        for x in range(xmin, xmax + 1)
        if comb(n1, x) * comb(n2, total - x) <= numerator_observed
    )
    return p_numerator / denominator


def fisher_three_by_two_equal_groups(success_counts: tuple[int, int, int], n: int) -> float:
    """Exact Fisher-Freeman-Halton 3x2 by probability ordering, fixed margins."""
    if len(success_counts) != 3 or n < 1 or any(
        not isinstance(x, int) or x < 0 or x > n for x in success_counts
    ):
        raise ValueError("invalid 3x2 contingency")
    target = sum(success_counts)
    denominator = comb(3 * n, target)
    observed = prod(comb(n, x) for x in success_counts)
    mass = 0
    total_mass = 0
    for x in range(n + 1):
        for y in range(n + 1):
            z = target - x - y
            if 0 <= z <= n:
                numerator = comb(n, x) * comb(n, y) * comb(n, z)
                total_mass += numerator
                if numerator <= observed:
                    mass += numerator
    assert total_mass == denominator, "enumeration must cover all tables"
    return mass / denominator


def holm_adjust(pvalues: dict[str, float]) -> dict[str, float]:
    """Family-wise error correction, preserving Holm monotonicity."""
    if not pvalues or any(not 0 <= v <= 1 for v in pvalues.values()):
        raise ValueError("invalid p-values")
    sorted_items = sorted(pvalues.items(), key=lambda kv: (kv[1], kv[0]))
    previous = 0.0
    adjusted = {}
    for i, (label, p) in enumerate(sorted_items):
        previous = max(previous, min(1.0, (len(sorted_items) - i) * p))
        adjusted[label] = previous
    return {label: adjusted[label] for label in pvalues}


def audit() -> dict:
    assert tuple(sorted(SURVIVORS)) == IMPACT_ENERGIES
    assert tuple(sorted(SURVIVORS[5])) == SOC_PERCENT
    assert PER_STRATUM == 5
    assert (sum(SURVIVORS[3].values()), sum(SURVIVORS[5].values()), sum(SURVIVORS[7].values())) == (15, 9, 0)

    subgroup = []
    for soc in SOC_PERCENT:
        k = SURVIVORS[5][soc]
        interval = wilson(k, PER_STRATUM)
        subgroup.append({
            "impact_j": 5,
            "soc_percent": soc,
            "survived_one_week": k,
            "n_impacted": PER_STRATUM,
            "survival_fraction": k / PER_STRATUM,
            "wilson_95": [float(interval[0]), float(interval[1])],
        })

    global_p = fisher_three_by_two_equal_groups(
        tuple(SURVIVORS[5][soc] for soc in SOC_PERCENT), PER_STRATUM
    )
    planned_soc = {}
    for a, b in combinations(SOC_PERCENT, 2):
        label = f"{a}_vs_{b}_soc_percent"
        planned_soc[label] = fisher_two_sided(
            SURVIVORS[5][a], PER_STRATUM, SURVIVORS[5][b], PER_STRATUM
        )
    planned_energy = {}
    for a, b in combinations(IMPACT_ENERGIES, 2):
        label = f"{a}_vs_{b}_joule"
        planned_energy[label] = fisher_two_sided(
            sum(SURVIVORS[a].values()), 3 * PER_STRATUM,
            sum(SURVIVORS[b].values()), 3 * PER_STRATUM
        )

    return {
        "source": {
            "doi": DOI,
            "publisher": "Batteries, 2026, 12(6), 217",
            "section": "Methods 2.1-2.2 and Results 3.2",
            "url": "https://www.mdpi.com/2313-0105/12/6/217",
            "evidence_type": "published_aggregate_cell_counts_not_individual_traces"
        },
        "cohort": {
            "total_physically_impacted_cells": 45,
            "per_energy": 15,
            "survived_after_one_week_by_energy": {"3J": 15, "5J": 9, "7J": 0},
            "one_week_endpoint": "retained >3V after one week at 30C",
            "survival_measure_not_capacity_percent": True,
        },
        "five_j_soc_subgroups": subgroup,
        "five_j_global_exact_fixed_margin_p": global_p,
        "five_j_global_test": "probability_ordered_3x2_fisher_freeman_halton",
        "five_j_pairwise_fisher_two_sided_raw_p": planned_soc,
        "five_j_pairwise_holm_familywise_p": holm_adjust(planned_soc),
        "energy_pairwise_fisher_two_sided_raw_p": planned_energy,
        "energy_pairwise_holm_familywise_p": holm_adjust(planned_energy),
        "statistical_limits": {
            "source_study_small_n_per_soc": PER_STRATUM,
            "no_5j_soc_global_significance_at_0_05": global_p >= 0.05,
            "no_5j_pairwise_soc_holm_significance_at_0_05": all(
                p >= 0.05 for p in holm_adjust(planned_soc).values()
            ),
            "not_a_causal_soc_optimum": True,
            "post_impact_capacity_only_for_one_week_survivors": True,
            "seven_j_survivor_capacity_trajectory_identifiable": False,
            "unreleased_individual_cell_capacity_and_hppc": True,
            "do_not_replace_failed_cells_capacity_with_zero": True,
            "different_experiment_from_bayreuth_48_cell_aging": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = audit()
    assert not any(
        k.lower().startswith("predicted_capacity") for k in payload
    ), "Do not fabricate capacity predictions"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("EXACT_SOC_AND_ENERGY_SURVIVAL_PASS", args.output, "global_p", payload["five_j_global_exact_fixed_margin_p"])


if __name__ == "__main__":
    main()
