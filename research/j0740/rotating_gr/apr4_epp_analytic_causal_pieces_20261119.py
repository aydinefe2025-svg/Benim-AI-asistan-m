#!/usr/bin/env python3
"""Check APR4_EPP's published high-density polytrope pieces, not smoothed splines."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

PINNED_SHA256 = "2a63cd7f1e1c5a158bb3cc06ab4b51f4344a9a1e6bfaeec7f98937c3d5a5447f"
PINNED_BYTES = 72350


def audit(source: Path) -> dict:
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    table = np.loadtxt(source, dtype=np.float64)
    if table.shape != (1447, 2) or not np.isfinite(table).all():
        raise ValueError(f"unexpected APR4_EPP table shape/content: {table.shape}")
    pressure, energy = table.T
    if not (np.all(pressure > 0) and np.all(energy > 0)):
        raise ValueError("nonpositive source pressure or energy density")

    # The published modified APR4 has Gamma=3 beginning near rho=1.4e15
    # g/cm^3 and Gamma=2 above 1.61e15 g/cm^3. The density column is absent
    # from the LAL two-column table; the transition knots are mapped by P,eps.
    pieces = []
    for name, gamma, start, stop in (
        ("added_Gamma_3", 3.0, 1413, 1419),
        ("added_Gamma_2", 2.0, 1419, 1446),
    ):
        p, e = pressure[start : stop + 1], energy[start : stop + 1]
        ratio = p / e
        cs2 = gamma * p / (e + p)
        if not np.all(np.diff(ratio) >= 0):
            raise ValueError(f"P/epsilon is not monotone in {name}; knot maximum is insufficient")
        pieces.append(
            {
                "name": name,
                "gamma": gamma,
                "source_rows_zero_based_inclusive": [start, stop],
                "pressure_range_geom_m2": [float(p[0]), float(p[-1])],
                "cs2_min_at_knots": float(cs2.min()),
                "cs2_max_at_knots": float(cs2.max()),
                "cs2_max_pressure_geom_m2": float(p[cs2.argmax()]),
                "p_over_epsilon_monotone_non_decreasing": True,
                "causal_on_piece_by_analytic_barotropic_relation": bool(np.all(cs2 < 1.0)),
            }
        )
    identity = len(raw) == PINNED_BYTES and digest == PINNED_SHA256
    return {
        "schema": "j0740_apr4_epp_causal_segment_correction_v1",
        "source": {
            "release": "LALSuite lalsuite-v7.26.4 APR4_EPP",
            "url": "https://git.ligo.org/lscsoft/lalsuite/-/raw/lalsuite-v7.26.4/lalsimulation/lib/LALSimNeutronStarEOS_APR4_EPP.dat",
            "bytes": len(raw),
            "sha256": digest,
            "pinned_identity_pass": identity,
            "rows": len(table),
        },
        "published_model_basis": {
            "reference": "Endrizzi et al. 2016, arXiv:1604.03445",
            "url": "https://arxiv.org/pdf/1604.03445",
            "reported_extension": "Gamma=3 segment beginning near 1.4e15 g cm^-3 and Gamma=2 above 1.61e15 g cm^-3, added to make modified APR4 causal",
            "formula": "cold polytrope: cs2 = Gamma*P/(epsilon+P), geometrized units",
        },
        "mapped_join": {
            "gamma3_start_row_zero_based": 1413,
            "join_row_zero_based": 1419,
            "join_pressure_geom_m2": float(pressure[1419]),
            "join_energy_geom_m2": float(energy[1419]),
            "boundary_evaluated_from_both_sides": True,
            "cs2_gamma3_at_join": float(3 * pressure[1419] / (energy[1419] + pressure[1419])),
            "cs2_gamma2_at_join": float(2 * pressure[1419] / (energy[1419] + pressure[1419])),
            "caveat": "The LAL table has no rest-mass-density column; density locations come from the cited model description, while row mapping uses source P,epsilon knots.",
        },
        "analytic_pieces": pieces,
        "correction_to_prior_report": {
            "withdrawn": "A natural-cubic or PCHIP derivative overshoot above cs2=1 proves the APR4_EPP source EOS is globally acausal.",
            "correct_interpretation": "Those values are diagnostics of the chosen smoothed interpolants. They smooth over intended piecewise-polytrope derivative changes and are not the analytic EOS sound speed.",
            "previous_interpolant_diagnostics_remain_valid_as_interpolant_diagnostics": True,
        },
        "acceptance": {
            "source_identity": identity,
            "added_Gamma3_piece_causal": pieces[0]["causal_on_piece_by_analytic_barotropic_relation"],
            "added_Gamma2_piece_causal": pieces[1]["causal_on_piece_by_analytic_barotropic_relation"],
            "all_original_APR4_crust_and_core_segments_independently_certified": False,
            "global_APR4_EPP_causality": "NOT_ESTABLISHED",
            "EOS_Bayes": "NOT_RUN",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(args.source)
    if not result["acceptance"]["source_identity"]:
        raise SystemExit("pinned source identity failed")
    if not result["acceptance"]["added_Gamma3_piece_causal"] or not result["acceptance"]["added_Gamma2_piece_causal"]:
        raise SystemExit("analytic high-density causal-piece check failed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source_sha256": result["source"]["sha256"], "pieces": result["analytic_pieces"], "global": "NOT_ESTABLISHED", "EOS_Bayes": "NOT_RUN"}, indent=2))


if __name__ == "__main__":
    main()

