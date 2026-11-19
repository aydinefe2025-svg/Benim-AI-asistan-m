#!/usr/bin/env python3
"""F73: independent, source-locked global BPS/F67 phase-admission test.

Only tests a *conditional* join of JESTER BPS with the distinct F67
MPA1_PCHIP_COLD surrogate, not the original nuclear MPA1 or a full EOS.
At T=0, competing phases must match pressure and baryon chemical potential;
the inward (higher-pressure) phase needs a non-decreasing baryon density.
A single BPS -> core transition must leave the core preferred at every
higher pressure for which both tabulated descriptions are available.

A phase crossing inferred from finite BPS knots is NOT a physical EOS proof.
No fitted or modified source EOS, fabricated TOV, or Bayes posterior is made.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import numpy as np
from scipy.optimize import brentq
from scipy.interpolate import PchipInterpolator

HERE = Path(__file__).resolve().parent
PHYS = HERE.parent / "physical_eos_validation"
F67_SHA = "d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22"
BPS_SHA = "a4195d48ae98fd64d0a9676891ccab5a5c035e713780ad1187e85571a98a1787"
NATIVE_BPS_NPZ_SHA = "372ce088e061997f7c05594e61e7c624a112d7ce66443c28c4633d03b7da6137"
NATIVE_MPA1_NPZ_SHA = "0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22"
MODEL = "BPS_OUTER_PLUS_F67_SEPARATE_CORE_PHASE_SELECTION_DIAGNOSTIC_NOT_PHYSICAL_EOS"
G, C = 6.67430e-11, 299792458.0
GEOM_PER_MEV_FM3 = 1.602176634e32 * G / C**4
MU_SURFACE_MEV = 930.4


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def energy_jump_requirement(e_core: float, e_bps: float, p: float, mu: float, n_bps: float):
    """At matched P and µ, a strictly inward density rise requires e_core>e_bps.

    This criterion is independent of baryon normalization (a forced choice of µ0).
    """
    if not all(math.isfinite(v) and v > 0 for v in (e_core, e_bps, p, mu, n_bps)):
        raise ValueError("non-positive state")
    n_core_forced = (e_core + p) / mu
    delta = e_bps - e_core
    return {"n_core_if_mu_matched_fm-3": n_core_forced,
            "density_jump_core_minus_crust_fm-3": n_core_forced - n_bps,
            "energy_deficit_e_bps_minus_e_core_MeV_fm-3": delta,
            "relative_energy_deficit_vs_bps": delta/e_bps,
            "inward_density_step_admissible_at_mu_match": bool(n_core_forced >= n_bps)}


def sign_brackets(p, delta_mu, *, pressure_floor: float = 1e-4):
    if len(p) != len(delta_mu) or len(p) < 2:
        raise ValueError("invalid sample alignment")
    p = np.asarray(p, dtype=float)
    d = np.asarray(delta_mu, dtype=float)
    if np.any(~np.isfinite(p)) or np.any(~np.isfinite(d)) or np.any(np.diff(p) <= 0):
        raise ValueError("non-monotone or nonfinite pressure / chemical potential")
    out=[]
    for i in range(len(p)-1):
        if p[i+1] < pressure_floor or d[i]*d[i+1] >= 0: continue
        out.append({"lower_knot": i, "upper_knot": i+1,
                    "pressure_interval_MeV_fm-3": [float(p[i]), float(p[i+1])],
                    "endpoint_delta_mu_MeV": [float(d[i]), float(d[i+1])],
                    "crossing_is_not_physical_confirmation": True})
    return out


def no_global_single_crust_to_core_transition(p, delta_mu, *, pressure_floor=1e-4):
    """If the core loses at the highest shared P, it cannot remain global
    thermodynamic minimum after any earlier BPS->core single switch.

    Includes no assumption about interpolation between source knots.
    """
    b = sign_brackets(p, delta_mu, pressure_floor=pressure_floor)
    upper = float(np.asarray(delta_mu, dtype=float)[-1])
    return {"single_switch_to_core_compatible_with_upper_endpoint": bool(upper <= 0),
            "core_minus_crust_mu_at_last_native_BPS_knot_MeV": upper,
            "candidate_sign_change_brackets_in_scanned_range": b,
            "exclusion_reason": ("CORE_HAS_HIGHER_GIBBS_PER_BARYON_AT_BPS_UPPER_ENDPOINT"
                                 if upper > 0 else "UPPER_ENDPOINT_DOES_NOT_EXCLUDE_SWITCH"),
            "scope_note": "BPS tabulated overlap only; lower-pressure knot discreteness and interpolants do not establish microscopic phase coexistence"}


def _load_hybrid_module(module_path):
    spec=importlib.util.spec_from_file_location("f73_conditional_hybrid", module_path)
    if spec is None or spec.loader is None: raise RuntimeError("missing declared F67 EOS code")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def calculate(bps_path: Path, core_path: Path, hybrid_path: Path):
    if sha256(bps_path) != BPS_SHA: raise ValueError("F73_BPS_BYTES_DRIFT")
    if sha256(core_path) != F67_SHA: raise ValueError("F73_F67_BYTES_DRIFT")
    bps=np.loadtxt(bps_path,delimiter=",",skiprows=1,dtype=float)
    if bps.shape!=(130,3) or np.any(~np.isfinite(bps)) or np.any(bps<=0):
        raise ValueError("F73_BPS_BAD_SHAPE_OR_VALUES")
    n_bps,p_bps,e_bps=bps.T
    if any(np.any(np.diff(v)<=0) for v in (n_bps,p_bps,e_bps)):
        raise ValueError("F73_BPS_NONMONOTONIC_SOURCE")
    mod = _load_hybrid_module(hybrid_path)
    eos=mod.EOS(core_path,subdivisions=2,quadrature=24)
    if abs(mod.MU0_MEV-MU_SURFACE_MEV)>1e-10:
        raise ValueError("F73_UNDECLARED_CORE_MU0")
    if np.any(p_bps*GEOM_PER_MEV_FM3<eos.p0) or np.any(p_bps*GEOM_PER_MEV_FM3>eos.pt):
        raise ValueError("F73_BPS_RANGE_OUTSIDE_F67_CORE_TABLE")
    ep=[];mu_core=[];nb_core=[]
    for p in p_bps:
        pg=float(p*GEOM_PER_MEV_FM3)
        logpg=math.log(pg)
        eg=math.exp(float(eos.spline(logpg)))
        m=MU_SURFACE_MEV*math.exp(eos.enthalpy_at_logp(logpg))
        ee=eg/GEOM_PER_MEV_FM3
        ep.append(ee)
        mu_core.append(m)
        nb_core.append((ee+p)/m)
    ep=np.asarray(ep)
    mu_core=np.asarray(mu_core)
    nb_core=np.asarray(nb_core)
    mu_bps=(e_bps+p_bps)/n_bps
    dmu=mu_core-mu_bps
    upper=energy_jump_requirement(float(ep[-1]),float(e_bps[-1]),float(p_bps[-1]),
                                  float(mu_bps[-1]),float(n_bps[-1]))
    upper.update({"P_MeV_fm-3":float(p_bps[-1]),
                  "mu_bps_MeV":float(mu_bps[-1]),"mu_core_MeV_at_930p4":float(mu_core[-1]),
                  "e_bps_MeV_fm-3":float(e_bps[-1]),"e_f67_MeV_fm-3":float(ep[-1]),
                  "n_bps_fm-3":float(n_bps[-1]),
                  "n_f67_at_930p4_fm-3":float(nb_core[-1]),
                  "mu0_required_for_mu_matching_endpoint_MeV":
                      float(MU_SURFACE_MEV*mu_bps[-1]/mu_core[-1])})
    if not (3.338 < upper["energy_deficit_e_bps_minus_e_core_MeV_fm-3"] < 3.340
            and upper["density_jump_core_minus_crust_fm-3"] < 0
            and .27 < mu_core[-1]-mu_bps[-1] < .30):
        raise AssertionError("F73_CORE_BPS_ENDPOINT_CROSSWALK_CHANGED")
    verdict = no_global_single_crust_to_core_transition(p_bps,dmu)
    if verdict["single_switch_to_core_compatible_with_upper_endpoint"]:
        raise AssertionError("F73_UPPER_PHASE_PREFERENCE_CHANGED")
    # Interpolation diagnostics ONLY. Roots are not used as physical EOS joins.
    raw_brackets=verdict["candidate_sign_change_brackets_in_scanned_range"]
    lp=np.log(p_bps)
    mu_bps_pchip=PchipInterpolator(lp,mu_bps,extrapolate=False)
    n_bps_pchip=PchipInterpolator(lp,np.log(n_bps),extrapolate=False)
    for b in raw_brackets:
        i,j=b["lower_knot"],b["upper_knot"]
        # Source-fidelity PCHIP of logE, and first-law H(P), not linear interpolation
        def diff(logp):
            pg=math.exp(logp)*GEOM_PER_MEV_FM3
            return (MU_SURFACE_MEV*math.exp(eos.enthalpy_at_logp(math.log(pg)))
                    -float(mu_bps_pchip(logp)))
        x=brentq(diff,float(lp[i]),float(lp[j]),xtol=1e-12)
        pc=math.exp(x)
        eps=float(math.exp(float(eos.spline(math.log(pc*GEOM_PER_MEV_FM3))))/GEOM_PER_MEV_FM3)
        mu=float(mu_bps_pchip(x))
        nc=(eps+pc)/mu
        ncrust=float(math.exp(float(n_bps_pchip(x))))
        b["Pchip_root_P_MeV_fm-3_NOT_NATIVE_PHASE_TRANSITION"] = pc
        b["Pchip_delta_n_core_minus_crust_fm-3"] = nc-ncrust
        b["Pchip_positive_inward_density_jump"] = bool(nc >= ncrust)
        b["Pchip_interpolation_is_a_discretization_choice"] = True
    return {"schema":"J0740_F73_BPS_F67_GIBBS_FIRST_ORDER_TRANSITION_GATE_V1",
            "status":"NUMERIC_SOURCE_LOCK_PASS_SINGLE_GLOBALLY_STABLE_BPS_F67_SWITCH_EXCLUDED",
            "model":MODEL,
            "source":{"F67_sha256":sha256(core_path),"BPS_csv_sha256":sha256(bps_path),
                      "BPS_JESTER_original_npz_sha256":NATIVE_BPS_NPZ_SHA,
                      "MPA1_JESTER_original_npz_sha256":NATIVE_MPA1_NPZ_SHA,
                      "F67_source_rows":len(eos.p),"BPS_source_rows":len(p_bps),
                      "source_files_mutated":False},
            "thermo_assumptions":{"mu_surface_MeV":MU_SURFACE_MEV,
                    "F67_enthalpy_and_E": "source-pinned PCHIP log(E) and independent first-law H(P)",
                    "BPS_mu": "(epsilon+P)/n from original 130 pressure knots",
                    "phase_stability":"at fixed P compare Gibbs energy per baryon mu, lower wins",
                    "density_step":"at equal mu and P require core n >= crust n as P increases inward"},
            "at_native_BPS_upper_endpoint":upper,
            "candidate_brackets_and_global_gate":verdict,
            "phase_preference_at_BPS_upper_endpoint":"BPS_LOWER_MU_CORE_NOT_GLOBAL_MINIMUM",
            "normalizing_mu0_only_cannot_fix_endpoint_density_inversion":True,
            "BPS_outer_crust_only":"TRUE_NOT_A_COMPLETE_INNER_CRUST",
            "physical_original_MPA1_certification":"NOT_ESTABLISHED",
            "matched_full_BPS_inner_crust_core_tov":"NOT_RUN",
            "matched_full_BPS_inner_crust_core_rotating_RNS":"NOT_RUN",
            "source_native_XPSI_and_seven_original_EOS_Bayes":"NOT_RUN",
            "limits":["No core chemical-potential normalization chosen from observational data",
                      "BPS knot sampling and compositions may require dedicated first-law smooth branch interpolation",
                      "Interpolated zero crossings are NOT proof of a valid phase transition",
                      "Excludes only the specified F67 930.4 MeV normalization and one transition over the tabulated BPS pressure range",
                      "Cannot infer original nuclear MPA1 microphysics from an exploratory F67 surrogate"],
            "interpretation":"The endpoint density inversion is independent of choosing mu0 to match chemical potential: at equal P and mu it follows solely from the lower F67 energy density. A globally favored single crust->core phase switch before BPS upper P is impossible under adopted source normalization because the crust has lower mu again at the uppermost shared P."}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--bps",type=Path,default=PHYS/"JESTER_BPS_crust_e6768650.csv")
    parser.add_argument("--f67",type=Path,default=PHYS/"F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat")
    parser.add_argument("--hybrid",type=Path,default=PHYS/"mpa1_jester_hybrid_crust_tov.py")
    parser.add_argument("--out",type=Path,required=True)
    a=parser.parse_args()
    obj=calculate(a.bps,a.f67,a.hybrid)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(obj,sort_keys=True,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"status":obj["status"],"endpoint":obj["at_native_BPS_upper_endpoint"],
        "candidate_count":len(obj["candidate_brackets_and_global_gate"]["candidate_sign_change_brackets_in_scanned_range"])},sort_keys=True))

if __name__=="__main__":main()
