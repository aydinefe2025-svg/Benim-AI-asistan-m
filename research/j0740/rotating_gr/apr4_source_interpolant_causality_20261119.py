#!/usr/bin/env python3
"""Independent APR4 source-table causality check; no EOS repair is applied."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline, PchipInterpolator


PINNED_SHA256 = "2a63cd7f1e1c5a158bb3cc06ab4b51f4344a9a1e6bfaeec7f98937c3d5a5447f"
PINNED_BYTES = 72350
TARGET_CENTRAL_PRESSURES = [
    5.331407604242784e-10,
    5.331403453467428e-10,
    5.340319524099945e-10,
    5.340319503159023e-10,
]


def evaluate(path: Path) -> dict:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    data = np.loadtxt(path, dtype=np.float64)
    if data.ndim != 2 or data.shape[1] != 2:
        raise ValueError(f"expected two-column table, got {data.shape}")
    pressure, energy = data.T
    if not (np.all(np.isfinite(data)) and np.all(pressure > 0) and np.all(energy > 0)):
        raise ValueError("table contains non-finite or non-positive P/epsilon")
    if not (np.all(np.diff(pressure) > 0) and np.all(np.diff(energy) > 0)):
        raise ValueError("source table is not strictly increasing in P and epsilon")

    x, y = np.log(pressure), np.log(energy)
    # Resolve each source interval with 100 evaluation points, including both endpoints.
    xx = np.concatenate([np.linspace(x[i], x[i + 1], 101)[:-1] for i in range(len(x) - 1)] + [x[-1:]])
    results = {}
    for label, interpolator in (
        ("natural_cubic", CubicSpline(x, y, bc_type="natural")),
        ("monotone_pchip", PchipInterpolator(x, y)),
    ):
        slope = interpolator.derivative()(xx)
        cs2 = np.exp(xx - interpolator(xx)) / slope
        if not np.all(np.isfinite(cs2)) or not np.all(slope > 0):
            raise ValueError(f"{label} failed finite positive-slope thermodynamic screen")
        maximum = int(np.argmax(cs2))
        violating = np.flatnonzero(cs2 > 1.0)
        results[label] = {
            "positive_dlogepsilon_dlogp_everywhere": bool(np.all(slope > 0)),
            "max_cs2": float(cs2[maximum]),
            "pressure_at_max_geom_m2": float(np.exp(xx[maximum])),
            "cs2_gt_1_grid_points": int(violating.size),
            "first_cs2_gt_1_pressure_geom_m2": float(np.exp(xx[violating[0]])) if violating.size else None,
            "last_cs2_gt_1_pressure_geom_m2": float(np.exp(xx[violating[-1]])) if violating.size else None,
            "global_causality_pass": bool(not violating.size),
        }

    raw_log_slope = np.diff(y) / np.diff(x)
    first_crossings = {
        name: value["first_cs2_gt_1_pressure_geom_m2"]
        for name, value in results.items()
    }
    target_max = max(TARGET_CENTRAL_PRESSURES)
    native_first = results["natural_cubic"]["first_cs2_gt_1_pressure_geom_m2"]
    return {
        "schema": "j0740_apr4_original_table_interpolant_causality_v1",
        "classification": "INDEPENDENT_SOURCE_TABLE_INTERPOLANT_DIAGNOSTIC; NO EOS REPAIR",
        "source": {
            "retrieval_url": "https://git.ligo.org/lscsoft/lalsuite/-/raw/lalsuite-v7.26.4/lalsimulation/lib/LALSimNeutronStarEOS_APR4_EPP.dat",
            "release": "LALSuite lalsuite-v7.26.4",
            "bytes": len(raw),
            "sha256": digest,
            "matches_pinned_source_identity": len(raw) == PINNED_BYTES and digest == PINNED_SHA256,
            "rows": int(len(data)),
            "columns": ["pressure_geom_m2", "energy_density_geom_m2"],
            "source_pressure_and_energy_strictly_increasing": True,
            "raw_dlogepsilon_dlogp_min": float(raw_log_slope.min()),
            "raw_dlogepsilon_dlogp_max": float(raw_log_slope.max()),
        },
        "method": {
            "cs2_definition": "(P/epsilon)/(d ln epsilon/d ln P), geometrized units",
            "natural_cubic": "SciPy natural cubic spline of log(epsilon) versus log(P)",
            "monotone_pchip": "SciPy shape-preserving PCHIP of log(epsilon) versus log(P); diagnostic only",
            "evaluation": "101 equally spaced points per adjacent source interval, including final endpoint",
            "no_clipping_or_causal_repair": True,
        },
        "interpolants": results,
        "target_star_context": {
            "source_record": "J0740_APR4_TARGET_STAR_CAUSALITY_20261118.json",
            "four_saved_rns_root_central_pressures_geom_m2": TARGET_CENTRAL_PRESSURES,
            "maximum_saved_target_central_pressure_geom_m2": target_max,
            "native_first_superluminal_pressure_geom_m2": native_first,
            "target_centres_below_native_first_superluminal_band": bool(native_first is not None and target_max < native_first),
            "interpretation": "Previously saved target-root interior screen is local to each star; it does not establish global APR4 causality.",
        },
        "acceptance": {
            "pinned_source_identity": len(raw) == PINNED_BYTES and digest == PINNED_SHA256,
            "raw_table_monotonicity": True,
            "natural_spline_global_causality": results["natural_cubic"]["global_causality_pass"],
            "pchip_global_causality": results["monotone_pchip"]["global_causality_pass"],
            "original_apr4_global_causality": bool(results["natural_cubic"]["global_causality_pass"] and results["monotone_pchip"]["global_causality_pass"]),
            "EOS_Bayes": "NOT_RUN",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "source_sha256": result["source"]["sha256"],
        "source_identity_pass": result["acceptance"]["pinned_source_identity"],
        "natural_cubic_max_cs2": result["interpolants"]["natural_cubic"]["max_cs2"],
        "pchip_max_cs2": result["interpolants"]["monotone_pchip"]["max_cs2"],
        "natural_first_violation_pressure": result["interpolants"]["natural_cubic"]["first_cs2_gt_1_pressure_geom_m2"],
        "pchip_first_violation_pressure": result["interpolants"]["monotone_pchip"]["first_cs2_gt_1_pressure_geom_m2"],
        "target_centres_below_violation_band": result["target_star_context"]["target_centres_below_native_first_superluminal_band"],
        "EOS_Bayes": "NOT_RUN",
    }, indent=2))


if __name__ == "__main__":
    main()
