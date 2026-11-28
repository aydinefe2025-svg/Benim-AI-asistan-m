#!/usr/bin/env python3
"""Independent dense checks of the reconstructed APR4_EPP analytic segments."""
from __future__ import annotations

import importlib.util
import json
import platform
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "reconstruct_apr4_epp_source_model_20261119.py"
OUT = ROOT / "J0740_APR4_EPP_ANALYTIC_SEGMENTS_INDEPENDENT_TEST_20261119.json"


def main() -> None:
    spec = importlib.util.spec_from_file_location("apr4_source_reconstruction", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    segments = module.build_segments()
    assert len(segments) == 9

    sampled = 0
    max_cs2 = 0.0
    for segment in segments:
        low = max(segment["lo"], 1e-30)
        high = segment["hi"] if np.isfinite(segment["hi"]) else low * 1e5
        rho = np.geomspace(low, high, 1000)
        pressure = segment["k"] * rho**segment["gamma"]
        epsilon = (1 + segment["a"]) * rho + pressure / (segment["gamma"] - 1)
        cs2 = segment["gamma"] * pressure / (epsilon + pressure)
        enthalpy = np.log((epsilon + pressure) / rho)
        assert segment["gamma"] > 0 and 1 + segment["a"] > 0
        assert np.all(np.isfinite(epsilon)) and np.all(epsilon > 0)
        assert np.all(np.isfinite(cs2)) and np.all(cs2 > 0) and np.all(cs2 <= 1 + 1e-12)
        assert np.all(np.diff(enthalpy) >= -1e-12)
        sampled += len(rho)
        max_cs2 = max(max_cs2, float(cs2.max()))

    pressure_jump = energy_jump = enthalpy_jump = 0.0
    for left, right in zip(segments[:-1], segments[1:]):
        rho = left["hi"]
        p_left = left["k"] * rho**left["gamma"]
        p_right = right["k"] * rho**right["gamma"]
        e_left = (1 + left["a"]) * rho + p_left / (left["gamma"] - 1)
        e_right = (1 + right["a"]) * rho + p_right / (right["gamma"] - 1)
        h_left = np.log((e_left + p_left) / rho)
        h_right = np.log((e_right + p_right) / rho)
        pressure_jump = max(pressure_jump, abs(p_right / p_left - 1))
        energy_jump = max(energy_jump, abs(e_right / e_left - 1))
        enthalpy_jump = max(enthalpy_jump, abs(h_right - h_left))
    assert pressure_jump <= 3e-7 and energy_jump <= 3e-7 and enthalpy_jump <= 3e-7

    result = {
        "schema": "j0740_apr4_analytic_segments_independent_test_v1",
        "runtime": {"python": platform.python_version(), "numpy": np.__version__},
        "method": "Independent 1000-point log-density sweep per analytic segment plus direct one-sided join checks.",
        "counts": {"segments": len(segments), "sampled_states": sampled, "joins": len(segments) - 1},
        "maxima": {
            "sampled_cs2": max_cs2,
            "relative_pressure_join_jump": pressure_jump,
            "relative_energy_join_jump": energy_jump,
            "absolute_enthalpy_join_jump": enthalpy_jump,
        },
        "acceptance": {
            "positive_energy_density": "PASS",
            "positive_subcausal_sound_speed": "PASS",
            "monotonic_enthalpy_with_density": "PASS",
            "rounded_source_join_tolerance_3e-7": "PASS",
            "APR4_EPP_physical_source_model": "PASS_RECONSTRUCTED_ANALYTIC_MODEL",
            "absolute_baryon_normalization": "NOT_ESTABLISHED",
            "rotating_continuous_stability": "NOT_ESTABLISHED",
            "EOS_Bayes": "NOT_RUN",
        },
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
