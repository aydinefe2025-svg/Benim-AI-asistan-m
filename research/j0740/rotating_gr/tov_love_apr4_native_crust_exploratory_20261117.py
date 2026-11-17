"""Exploratory independent TOV-Love integration for APR4_EPP; not EOS certification."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import argparse

import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq

SOURCE = Path(r"C:\Users\User\AppData\Local\SentinelX\uploads\j0740_20261117_sources\APR4_EPP.npz")
OUT = Path(r"C:\Users\User\AppData\Local\SentinelX\workspace\J0740_APR4_LOCAL_REPLICATION_20261117\J0740_APR4_TOV_LOVE_EXPLORATORY_20261117.json")
SOURCE_SHA = "639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88"
G = 6.67430e-11
C_LIGHT = 299792458.0
MSUN_GEOM_M = 1476.6250385
TARGET_MSUN = 2.073
RHO_SI = np.array([0.0, 2.44033979e10, 3.78358138e14, 2.62780487e15])
K_SI = np.array([1.0801158752700761e7, 1.311359898998385e10, 6.507604807550857e19, 3.053461077133694e8])
GAMMA = np.array([1.58424999, 1.28732904, 0.62223344, 1.35692395])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class EOS:
    def __init__(self, source: Path):
        if sha256(source) != SOURCE_SHA:
            raise ValueError("APR4 source checksum mismatch")
        z = np.load(source, allow_pickle=False)
        self.p = np.asarray(z["p"], float)
        self.e = np.asarray(z["e"], float)
        self.h = np.asarray(z["h"], float)
        self.n_source = np.asarray(z["n"], float)
        if any(np.any(np.diff(x) <= 0) or not np.isfinite(x).all() for x in (self.p, self.e, self.h, self.n_source)):
            raise ValueError("source EOS arrays failed finite/monotone checks")
        self.lp = np.log(self.p)
        self.le = np.log(self.e)
        self.e_interp = PchipInterpolator(self.lp, self.le, extrapolate=False)
        self.h_interp = PchipInterpolator(self.lp, self.h, extrapolate=False)
        self.rho_g = G * RHO_SI / C_LIGHT**2
        self.k_g = K_SI * G ** (1.0 - GAMMA) * C_LIGHT ** (2.0 * GAMMA - 4.0)
        self.poly_n = 1.0 / (GAMMA - 1.0)
        self.a = np.zeros(4)
        self.pb = self.k_g[1:] * self.rho_g[1:] ** GAMMA[1:]
        for i in range(1, 4):
            self.a[i] = self.a[i - 1] + (self.poly_n[i - 1] - self.poly_n[i]) * self.pb[i - 1] / self.rho_g[i]
        self.mu0 = float(np.median(self.e / self.n_source))

    def values(self, p: float):
        p = max(float(p), 1e-100)
        if p < self.p[0]:
            i = max(0, int(np.searchsorted(np.r_[0.0, self.pb], p, side="left") - 1))
            rho = (p / self.k_g[i]) ** (1.0 / GAMMA[i])
            e = (1.0 + self.a[i]) * rho + self.poly_n[i] * p
            h = math.log(1.0 + self.a[i] + (self.poly_n[i] + 1.0) * p / rho)
            cs2 = GAMMA[i] * p / (e + p)
        else:
            lp = math.log(p)
            e = math.exp(float(self.e_interp(lp)))
            slope = float(self.e_interp.derivative()(lp))
            h = float(self.h_interp(lp))
            cs2 = p / (e * slope)
        rho_b = (e + p) * math.exp(-h)
        return e, h, cs2, rho_b


def love_k2(compactness: float, y: float) -> float:
    c = compactness
    a = (8.0 * c**5 / 5.0) * (1.0 - 2.0*c)**2 * (2.0 + 2.0*c*(y - 1.0) - y)
    den = (
        2.0*c*(6.0 - 3.0*y + 3.0*c*(5.0*y - 8.0))
        + 4.0*c**3*(13.0 - 11.0*y + c*(3.0*y - 2.0) + 2.0*c**2*(1.0 + y))
        + 3.0*(1.0 - 2.0*c)**2*(2.0 - y + 2.0*c*(y - 1.0))*math.log1p(-2.0*c)
    )
    return a / den


def solve_star(eos: EOS, pc: float, max_step: float, rtol: float = 2e-9):
    ec, _, _, rhoc = eos.values(pc)
    r0 = 1e-3
    m0 = 4.0 * math.pi * ec * r0**3 / 3.0
    b0 = 4.0 * math.pi * rhoc * r0**3 / 3.0
    y0 = 2.0
    p_surface = 1e-27

    def rhs(r, state):
        m, p, y, mb = state
        p_eval = max(p, p_surface)
        e, h, cs2, rho_b = eos.values(p_eval)
        den = 1.0 - 2.0*m/r
        grav = (m + 4.0*math.pi*r**3*p_eval) / den
        dp = -(e + p_eval) * grav / (r*r)
        dm = 4.0*math.pi*r*r*e
        db = 4.0*math.pi*r*r*rho_b / math.sqrt(max(den, 1e-30))
        f = (1.0 - 4.0*math.pi*r*r*(e - p_eval)) / den
        q = (4.0*math.pi*(5.0*e + 9.0*p_eval + (e+p_eval)/max(cs2, 1e-30))/den
             - 6.0/(r*r) - 4.0*grav**2/(r**4))
        dy = -(y*y + y*f + r*r*q)/r
        return [dm, dp, dy, db]

    def surface(r, state):
        return state[1] - p_surface
    surface.terminal = True
    surface.direction = -1
    sol = solve_ivp(rhs, (r0, 5.0e5), [m0, pc, y0, b0], method="DOP853",
                    rtol=rtol, atol=[1e-9, 1e-30, 1e-10, 1e-9], max_step=max_step,
                    events=surface)
    if not sol.success or len(sol.t_events[0]) != 1:
        raise RuntimeError("TOV integration did not reach the pressure-floor surface: " + sol.message
                           + f"; r={sol.t[-1]:.16g}; state={sol.y[:,-1].tolist()}; surface={p_surface:.4g}")
    radius = float(sol.t_events[0][0])
    mass, _, y, mb = [float(x) for x in sol.y_events[0][0]]
    compactness = mass/radius
    k2 = love_k2(compactness, y)
    lam = 2.0*k2/(3.0*compactness**5)
    return {"Mg_msun": mass/MSUN_GEOM_M, "Mb_msun_candidate": mb/MSUN_GEOM_M,
            "R_km": radius/1000.0, "Lambda": lam, "k2": k2,
            "central_pressure_geom_m_inv2": pc, "central_e_geom_m_inv2": ec,
            "central_cs2": eos.values(pc)[2], "surface_y": y, "n_steps": int(len(sol.t)),
            "rtol": rtol, "max_step_m": max_step}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args(argv)
    source = args.source
    output = args.output
    if output.exists():
        raise FileExistsError("refusing to overwrite prior TOV-Love evidence")
    eos = EOS(source)
    # Use existing APR4 RNS/TOV center only to bracket a target-M shooting solve.
    center_rho_gcm3 = np.array([1.45e15, 1.65e15, 1.80e15, 2.00e15, 2.20e15])
    center_e = G * (center_rho_gcm3 * 1000.0) / C_LIGHT**2
    logpc = np.interp(np.log(center_e), eos.le, eos.lp)
    scan = []
    for lp in logpc:
        s = solve_star(eos, math.exp(float(lp)), max_step=250.0, rtol=2e-8)
        scan.append({"center_rho_g_cm3": float(np.exp(np.interp(lp, eos.lp, eos.le))*C_LIGHT**2/G/1000),
                     "Mg_msun": s["Mg_msun"], "R_km": s["R_km"]})
    brackets = [(i, i+1) for i in range(len(scan)-1) if (scan[i]["Mg_msun"]-TARGET_MSUN)*(scan[i+1]["Mg_msun"]-TARGET_MSUN) <= 0]
    if len(brackets) != 1:
        raise RuntimeError("target mass did not have one unique bracket on the scanned branch: " + repr(scan))
    ia, ib = brackets[0]
    lo, hi = float(logpc[ia]), float(logpc[ib])
    results = []
    for step in (400.0, 200.0, 100.0):
        def residual(lp):
            return solve_star(eos, math.exp(lp), max_step=step, rtol=2e-9)["Mg_msun"] - TARGET_MSUN
        root = brentq(residual, lo, hi, xtol=2e-13, rtol=2e-13, maxiter=60)
        star = solve_star(eos, math.exp(root), max_step=step, rtol=2e-9)
        star["mass_root_residual_msun"] = star["Mg_msun"] - TARGET_MSUN
        results.append(star)
    fine = results[-1]
    deltas = {
        "delta_Mg_msun_fine_vs_previous": fine["Mg_msun"] - results[-2]["Mg_msun"],
        "delta_Mb_candidate_msun_fine_vs_previous": fine["Mb_msun_candidate"] - results[-2]["Mb_msun_candidate"],
        "delta_R_km_fine_vs_previous": fine["R_km"] - results[-2]["R_km"],
        "relative_delta_Lambda_fine_vs_previous": fine["Lambda"] / results[-2]["Lambda"] - 1.0,
    }
    doc = {
        "schema": "j0740-apr4-independent-tov-love-exploratory-v1",
        "status": "EXPLORATORY_TARGET_M_TOV_LOVE_ONLY; EOS_NOT_CERTIFIED; EOS_BAYES_NOT_RUN",
        "source": {"path": str(source), "bytes": source.stat().st_size, "sha256": SOURCE_SHA,
                   "rows": len(eos.p), "jester_commit": "e6768650ce992abfd1153a6833857572fe5cd230",
                   "lalsuite_generator_version": "unpinned"},
        "method": {"independent_solver": "SciPy solve_ivp DOP853 TOV + y-parameter Love ODE; PCHIP log(e)-log(P) source-table interpolation",
                   "crust": "LALSuite documented four-piece SLy low-density analytic reference; source table joined at first positive pressure",
                   "baryon_mass": "M_b from rho_b=(e+P)*exp(-h), with source h above table start and LAL crust h below; source n ignored",
                   "shooting_target_Mg_msun": TARGET_MSUN, "surface_pressure_floor_geom_m_inv2": 1e-27,
                   "spatial_max_steps_m": [400.0, 200.0, 100.0], "integrator_rtol": 2e-9},
        "bracketing_scan": scan, "solutions": results, "fine_vs_previous": deltas,
        "checks": {"three_spatial_step_sizes_completed": len(results)==3,
                   "mass_shooting_residual_below_1e-8_msun": all(abs(x["mass_root_residual_msun"])<1e-8 for x in results),
                   "central_cs2_below_causality": all(0.0 < x["central_cs2"] <= 1.0 for x in results),
                   "all_lambda_positive": all(x["Lambda"]>0 for x in results)},
        "limitations": ["This is a conditional tabulated-e(P) interpolation model, not a native LALSuite binary replay.",
                        "The table starts at positive pressure and the LALSuite producer version is unpinned.",
                        "The source n column is discarded; M_b is conditional on the h-based first-law density and its unresolved absolute normalization.",
                        "This is a static TOV-Love calculation, not a rotating RNS result or continuous stability proof.",
                        "No EOS prior normalization or EOS Bayes inference was evaluated."],
        "eos_bayes": "NOT_RUN",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(output), "bytes": output.stat().st_size, "sha256": sha256(output),
                      "status": doc["status"], "scan": scan, "solutions": results, "deltas": deltas,
                      "checks": doc["checks"]}, indent=2))


if __name__ == "__main__":
    main()

