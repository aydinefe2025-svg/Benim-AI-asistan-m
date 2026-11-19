"""Low-pressure APR4 power-law sensitivity, separate from EOS certification."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import warnings
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq


TARGET_M = 2.073
SURFACE_P = 1e-33
MSUN_GEOM_M = 1476.6250385


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("pinned_apr4_tov", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def solve_for_power(module, table: Path, alpha: float) -> dict:
    eos = module.NativeTable(table)
    h_surface_to_join = math.log1p(eos.ratio) / (1.0 - alpha)
    eos.delta_h = h_surface_to_join - eos.h0
    original_values = eos.values

    def values(p: float, corrected: bool = True):
        if p >= eos.p[0]:
            return original_values(p, corrected)
        x = p / eos.p[0]
        energy = eos.e[0] * x**alpha
        enthalpy = math.log1p(eos.ratio * x ** (1.0 - alpha)) / (1.0 - alpha)
        if not corrected:
            enthalpy = eos.h0 * x ** (1.0 - alpha)
        cs2 = alpha * p / energy
        return energy, enthalpy, cs2

    eos.values = values

    def bounded_star(logpc: float, step: float, corrected: bool = True, surface_p: float = SURFACE_P):
        pc = math.exp(logpc)
        ec, hc, central_cs2 = eos.values(pc, corrected)
        r0 = 0.01
        m0 = 4.0 * math.pi * ec * r0**3 / 3.0
        mb0 = 4.0 * math.pi * (ec + pc) * math.exp(-hc) * r0**3 / 3.0
        qsurf = math.log(surface_p)

        def rhs(r, state):
            m, q, y, mb = state
            p = math.exp(max(q, qsurf))  # bound event-crossing trial stages to the surface
            e, h, cs2 = eos.values(p, corrected)
            den = max(1.0 - 2.0 * m / r, 1e-15)
            grav = (m + 4.0 * math.pi * r**3 * p) / den
            dp = -(e + p) * grav / r**2
            dm = 4.0 * math.pi * r**2 * e
            rb = (e + p) * math.exp(-h)
            dmb = 4.0 * math.pi * r**2 * rb / math.sqrt(den)
            ff = (1.0 - 4.0 * math.pi * r**2 * (e - p)) / den
            Q = 4.0 * math.pi * (5.0 * e + 9.0 * p + (e + p) / max(cs2, 1e-30)) / den - 6.0 / (r*r*den) - 4.0 * grav**2 / r**4
            dy = -(y*y + y*ff + r*r*Q) / r
            return [dm, dp / p, dy, dmb]

        def surface(r, state):
            return state[1] - qsurf

        surface.terminal = True
        surface.direction = -1
        sol = solve_ivp(rhs, (r0, 1e6), [m0, logpc, 2.0, mb0], method="DOP853", rtol=2e-9,
                        atol=[1e-5, 1e-11, 1e-9, 1e-5], max_step=step, events=surface)
        if not sol.success or len(sol.t_events[0]) != 1:
            raise RuntimeError(sol.message)
        radius = sol.t_events[0][0]
        mass, _, y, mb = sol.y_events[0][0]
        compactness = mass / radius
        num = (8.0 * compactness**5 / 5.0) * (1.0 - 2.0 * compactness)**2 * (2.0 + 2.0 * compactness * (y - 1.0) - y)
        den = 2.0 * compactness * (6.0 - 3.0*y + 3.0*compactness*(5.0*y - 8.0)) + 4.0 * compactness**3 * (13.0 - 11.0*y + compactness*(3.0*y - 2.0) + 2.0*compactness**2*(1.0+y)) + 3.0*(1.0-2.0*compactness)**2*(2.0-y+2.0*compactness*(y-1.0))*math.log1p(-2.0*compactness)
        k2 = num / den
        return {"Mg_msun": mass / MSUN_GEOM_M, "R_km": radius / 1000.0, "k2": k2,
                "Lambda": (2.0/3.0)*k2/compactness**5, "Mb_conditional_msun": mb/MSUN_GEOM_M,
                "central_cs2": central_cs2, "Pc_geom_m2": pc, "ode_steps": len(sol.t)}

    root = brentq(lambda z: bounded_star(z, 200.0)["Mg_msun"] - TARGET_M,
                  math.log(1.4e-10), math.log(1.5e-9), xtol=2e-11, rtol=2e-12, maxiter=35)
    result = bounded_star(root, 200.0)
    result["surface_power_alpha"] = alpha
    result["mass_residual_msun"] = result["Mg_msun"] - TARGET_M
    return result


def run(table: Path, solver_path: Path) -> dict:
    module = load_module(solver_path)
    table_sha = hashlib.sha256(table.read_bytes()).hexdigest()
    if table_sha != module.TABLE_SHA:
        raise ValueError("official APR4 source table SHA mismatch")
    source = np.loadtxt(table)
    slopes = np.diff(np.log(source[:, 1])) / np.diff(np.log(source[:, 0]))
    alpha_source = float(np.median(slopes[:100]))
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        cases = [solve_for_power(module, table, a) for a in (0.6, alpha_source)]
    baseline, data_slope = cases
    delta = {key: data_slope[key] - baseline[key] for key in ("R_km", "Lambda", "Mb_conditional_msun", "Pc_geom_m2", "central_cs2")}
    passed = all(abs(row["mass_residual_msun"]) < 1e-8 for row in cases)
    return {
        "schema": "j0740_apr4_low_pressure_power_sensitivity_v1",
        "classification": "EXPLORATORY_CRUST_EXTENSION_SENSITIVITY; TABLE_SLOPE_IS_NOT_A_PHYSICAL_CRUST_CERTIFICATE",
        "source": {"lalsuite_tag": "lalsuite-v7.26.4", "table_bytes": table.stat().st_size, "table_sha256": table_sha,
                   "rows": int(len(source)), "first_pressure_geom_m2": float(source[0, 0]), "first_energy_geom_m2": float(source[0, 1]),
                   "alpha_median_first_100_source_secants": alpha_source},
        "method": {"target_gravitational_mass_msun": TARGET_M, "target_spin_hz": 0.0,
                   "surface_pressure_geom_m2": SURFACE_P, "grid_step_m": 200.0,
                   "first_law_enthalpy": "h(P)=ln[1+(P0/e0)(P/P0)^(1-alpha)]/(1-alpha), continuous at P0",
                   "event_stage_pressure_bounded_at_surface": True, "warnings_as_errors": True,
                   "alternative_is_extrapolation_diagnostic_not_a_data-derived_physical_crust": True},
        "cases": cases,
        "data_slope_minus_alpha_0p6": delta,
        "checks": {"official_source_hash": True, "both_mass_roots_within_1e-8_msun": passed,
                   "both_centres_causal": all(0 < row["central_cs2"] < 1 for row in cases),
                   "no_runtime_warnings": True, "EOS_Bayes": "NOT_RUN"},
        "interpretation": "The low-pressure exponent changes R, Lambda and conditional Mb only at tiny levels for this 2.073 Msun static star. This sensitivity does not establish the physical crust or absolute baryon normalization.",
        "status": "NUMERICAL_CRUST_SENSITIVITY_PASS; PHYSICAL_CRUST_NOT_ESTABLISHED; EOS_Bayes=NOT_RUN" if passed else "FAIL",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", type=Path, required=True)
    parser.add_argument("--solver", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.table, args.solver)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "status": report["status"], "checks": report["checks"],
                      "delta_R_km": report["data_slope_minus_alpha_0p6"]["R_km"],
                      "delta_Lambda": report["data_slope_minus_alpha_0p6"]["Lambda"],
                      "delta_Mb_msun": report["data_slope_minus_alpha_0p6"]["Mb_conditional_msun"]}, indent=2))


if __name__ == "__main__":
    main()
