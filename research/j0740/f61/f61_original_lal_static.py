"""F61: genuinely new source-native, unmodified 7-EOS LALSuite TOV mass roots.

Real LALSuite TOV ODE integration (not JESTER array interpolation for new stars).
Original JESTER NPZ serves as SHA-locked independent EOS/MR reference.
Never equate static TOV maximum with the maximum mass of a rotating star.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

G, C = 6.67430e-11, 299792458.0
RADIO_MEAN, RADIO_SIGMA = 2.082, .0703
TRUNCATE_SIGMA = 5.
PINNED_JESTER = "e6768650ce992abfd1153a6833857572fe5cd230"
TARGET_MASSES = (2.073, 2.175, 2.200, 2.225, 2.250)
EOS = ("APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def mass_prior_cdf(x):
    """Radio Gaussian with precisely normalized +/-5 sigma truncation."""
    z = (x - RADIO_MEAN) / RADIO_SIGMA
    if not math.isfinite(x):
        raise ValueError("NONFINITE_MASS")
    if z <= -TRUNCATE_SIGMA:
        return 0.
    if z >= TRUNCATE_SIGMA:
        return 1.
    cdf = lambda z: .5 * math.erfc(-z / math.sqrt(2.))
    return (cdf(z) - cdf(-TRUNCATE_SIGMA)) / (cdf(TRUNCATE_SIGMA) - cdf(-TRUNCATE_SIGMA))


def reference_static_branch(masses, radii):
    """Reject internal reversals in a selected ascending original JESTER TOV curve."""
    m, r = map(lambda x: np.asarray(x, dtype=float), (masses, radii))
    if (m.ndim != 1 or r.shape != m.shape or len(m) < 20
        or not np.isfinite(m).all() or not np.isfinite(r).all()
        or np.any(m <= 0) or np.any(r <= 0)):
        raise ValueError("MALFORMED_NATIVE_STATIC_SOURCE_MR")
    imax = int(np.argmax(m))
    imin = int(np.argmin(m[:imax + 1]))
    if imax - imin < 12 or np.any(np.diff(m[imin:imax+1]) <= 0):
        raise ValueError("NONMONOTONIC_NATIVE_STATIC_BRANCH")
    return m[imin:imax+1], r[imin:imax+1], {"native_mmax_msun": float(m[imax]),
        "native_min_stable_msun": float(m[imin]),
        "original_peak_index": imax,
        "original_low_mass_minimum_index": imin,
        "native_reference_points": int(len(m)),
        "reference_is_original_LAL_TOV_NOT_new_solution": True}


def positive_tov_result(pc_pa, radius_m, mass_kg, k2, solar_mass_kg):
    vals = [pc_pa, radius_m, mass_kg, k2, solar_mass_kg]
    if (not all(math.isfinite(float(v)) for v in vals)
        or pc_pa <= 0 or radius_m <= 0 or mass_kg <= 0 or solar_mass_kg <= 0
        or not 0 < k2 < 1):
        raise ValueError("INVALID_LAL_TOV_SOLUTION")
    mass_msun = mass_kg / solar_mass_kg
    if not (0 < mass_msun < 5):
        raise ValueError("INVALID_LAL_TOV_MASS")
    return {"mass_msun":float(mass_msun), "radius_km":float(radius_m/1000.),
            "love_k2":float(k2), "central_pressure_si_pa":float(pc_pa)}


def scan_native_source(solve_pc_pa, *, nscan=64, low_pa=1e32, high_pa=1.3e35):
    """Direct LAL TOV grid and explicit source-order ascending-branch test."""
    if nscan < 30 or not 0 < low_pa < high_pa:
        raise ValueError("INVALID_TOV_SCAN_CONFIG")
    samples, failed = [], []
    for pc in np.geomspace(low_pa, high_pa, nscan):
        try:
            star = solve_pc_pa(float(pc))
            if not (math.isfinite(star["mass_msun"]) and star["mass_msun"]>0):
                raise ValueError("INVALID_TOV_MASS")
            samples.append(star)
        except (ValueError, RuntimeError, OverflowError) as exc:
            failed.append({"pc_pa":float(pc),"reason":type(exc).__name__,"message":str(exc)[:190]})
    if len(samples) < 18:
        raise ValueError("INSUFFICIENT_DIRECT_NATIVE_TOV_ROOT_BRACKETS")
    masses = np.array([s["mass_msun"] for s in samples])
    imax=int(np.argmax(masses))
    imin=int(np.argmin(masses[:imax+1]))
    asc = samples[imin:imax+1]
    if len(asc) < 10 or np.any(np.diff(masses[imin:imax+1]) <= 0):
        raise ValueError("DIRECT_LAL_STABLE_BRANCH_NONMONOTONIC")
    return asc, samples, failed


def root_at_mass(solve_pc_pa, stable_asc, mass):
    """Solve genuinely native TOV root in central PRESSURE; no M/R interpolation."""
    if not (math.isfinite(mass) and 0 < mass < 5):
        raise ValueError("INVALID_TARGET_MASS")
    for lo, hi in zip(stable_asc[:-1], stable_asc[1:]):
        a, b = lo["mass_msun"] - mass, hi["mass_msun"] - mass
        if a == 0: return dict(lo)
        if a < 0 < b:
            p0, p1 = lo["central_pressure_si_pa"], hi["central_pressure_si_pa"]
            evaluations = []
            def difference(log10_pc):
                star = solve_pc_pa(10 ** log10_pc)
                evaluations.append({"p_pa":star["central_pressure_si_pa"], "M_msun":star["mass_msun"]})
                return star["mass_msun"] - mass
            rt=brentq(difference,math.log10(p0),math.log10(p1),xtol=5e-12,rtol=9e-14,maxiter=55)
            star=solve_pc_pa(10 ** rt)
            if abs(star["mass_msun"]-mass)>2e-7:
                raise ValueError("DIRECT_LAL_TOV_ROOT_RESIDUAL_TOO_LARGE")
            return dict(star, bracket_pc_pa=[p0,p1], direct_TOV_solver_calls_in_root=len(evaluations),
                        root_mass_residual_msun=star["mass_msun"]-mass,
                        native_TOV_not_source_interpolation=True)
        if b == 0: return dict(hi)
    return None


def source_physics_at_center(original_arrays, pc_pa, sound_speed_of_p_geom, *, core_rho_cgs=2.8e14):
    """Sample SOURCE analytic sound speed at JESTER knots plus direct center.

    A sampled causal core is *not* a proof between nodes, and the core screen
    does not silently dismiss a negative-cs2 source crust.
    """
    pp = np.asarray(original_arrays["p"],dtype=float)
    ee = np.asarray(original_arrays["e"],dtype=float)
    cc = np.asarray(original_arrays["cs2"],dtype=float)
    pcenter=pc_pa*G/C**4
    if (len(pp)<100 or pp.shape!=ee.shape or pp.shape!=cc.shape
        or not np.isfinite(pp).all() or not np.isfinite(ee).all() or not np.isfinite(cc).all()
        or np.any(pp<=0) or np.any(ee<=0) or np.any(np.diff(pp)<=0)
        or not pp[0]<pcenter<pp[-1]):
        raise ValueError("SOURCE_STAR_CENTER_OUTSIDE_THERMO_TABLE")
    ccentral=float(sound_speed_of_p_geom(pcenter))
    if not math.isfinite(ccentral):
        raise ValueError("NONFINITE_NATIVE_CORE_SOUND_SPEED")
    interior=pp<=pcenter
    cs=cc[interior]
    rho=ee[interior]*C*C/G*1e-3
    core=cs[rho>=core_rho_cgs]
    if len(core)<15:
        raise ValueError("INSUFFICIENT_CORE_CAUSALITY_NODES")
    core=np.r_[core,ccentral]
    full=np.r_[cs,ccentral]
    return {"central_cs2_over_c2_native_LAL_derivative":ccentral,
        "central_pressure_geom_m_minus_2":pcenter,
        "central_energy_rho_g_cm3_log_pressure_source_interpolated":float(
            np.interp(math.log(pcenter),np.log(pp),ee)*C*C/G*1e-3),
        "original_source_knots_below_center":int(interior.sum()),
        "sampled_full_interior_cs2_nonpositive":int(np.count_nonzero(full<=0)),
        "sampled_full_interior_cs2_superluminal":int(np.count_nonzero(full>1)),
        "sampled_core_cs2_nonpositive_above_2p8e14":int(np.count_nonzero(core<=0)),
        "sampled_core_cs2_superluminal_above_2p8e14":int(np.count_nonzero(core>1)),
        "sampled_core_max_cs2":float(max(core)),
        "sampled_core_min_cs2":float(min(core)),
        "sampled_core_screen":"SAMPLED_PASS_NOT_CONTINUOUS_OR_FULL_STAR_PROOF" if (core>0).all() and (core<=1).all() else "SAMPLED_FAIL",
        "full_interior_screen":"SAMPLED_PASS_NOT_CONTINUOUS_PROOF" if (full>0).all() and (full<=1).all() else "SAMPLED_FAIL",
        "original_microphysical_EOS_modified":False,
        "limitations":["Source analytical derivatives at JESTER pressure knots + exact native central derivative; not rigorous continuum extrema", "Subnuclear negative-cs2 source knots are NOT erased by the separate core-only screen", "Static star not observed-spin rotating star"]}


def run(source_dir, fixture, lal, lalsimulation, *, nscan=64):
    if fixture.get("source_commit") != PINNED_JESTER or set(fixture.get("eos",{}))!=set(EOS):
        raise ValueError("PINNED_SEVEN_SOURCE_IDENTITY_DRIFT")
    report={"schema":"F61_J0740_ORIGINAL_SEVEN_LALSUITE_STATIC_TOV_PHYSICAL_SCREEN_v1",
        "status":"DIRECT_NATIVE_STATIC_TOV_ONLY_NOT_ROTATING_OR_EOS_POSTERIOR",
        "jester_source_commit":PINNED_JESTER,
        "lalsuite_version":str(getattr(lal,"__version__","unknown")),
        "lalsimulation_version":str(getattr(lalsimulation,"__version__","unknown")),
        "target_masses_msun":TARGET_MASSES,
        "EOS_original_not_F42_modified":True,
        "source_provenance_failures":[],
        "targets_attempted_direct_native_LAL_TOV":[],
        "results":{}}
    for name in EOS:
        expected=fixture["eos"][name]
        path=Path(source_dir)/(name+".npz")
        if sha256(path)!=expected["expected_source_sha256"]:
            raise ValueError("SOURCE_HASH_DRIFT_"+name)
        with np.load(path,allow_pickle=False) as z:
            required={"p","e","cs2","masses_EOS","radii_EOS"}
            if not required.issubset(z.files):raise ValueError("SOURCE_MISSING_KEYS_"+name)
            arrays={key:np.asarray(z[key],float) for key in required}
        if len(arrays["p"])!=expected["expected_source_rows"]:
            raise ValueError("SOURCE_NODES_DRIFT_"+name)
        sm,sr,source_summary=reference_static_branch(arrays["masses_EOS"],arrays["radii_EOS"])
        native_eos=lalsimulation.SimNeutronStarEOSByName(name)
        @lru_cache(maxsize=1024)
        def solve(pc):
            rm,mkg,k2=lalsimulation.SimNeutronStarTOVODEIntegrate(pc,native_eos)
            return positive_tov_result(pc,rm,mkg,k2,lal.MSUN_SI)
        def source_cs2(pgeom):
            dp=lalsimulation.SimNeutronStarEOSEnergyDensityDerivOfPressureGeometerized(pgeom,native_eos)
            if not math.isfinite(float(dp)) or float(dp)==0:raise ValueError("NONPHYSICAL_NATIVE_SOUND_SPEED_DERIVATIVE")
            return 1/float(dp)
        asc,samples,failed=scan_native_source(solve,nscan=nscan)
        report["results"][name]={"source_npz_sha256":sha256(path),
            "source_static_reference":source_summary,
            "direct_LAL_sampled_ascending_branch_mass_range_msun":[asc[0]["mass_msun"],asc[-1]["mass_msun"]],
            "number_direct_static_TOV_scan_successes":len(samples),
            "number_direct_static_TOV_scan_failures":len(failed),
            "direct_static_TOV_failures":failed[:15],"stars":{}}
        for target in TARGET_MASSES:
            key=f"{target:.3f}"
            star=root_at_mass(solve,asc,target)
            if star is None:
                report["results"][name]["stars"][key]={
                    "status":"NOT_BRACKETED_ON_NATIVE_STATIC_ASCENDING_BRANCH",
                    "source_static_Mmax_msun":source_summary["native_mmax_msun"],
                    "rotation_346p536Hz_max_mass":"NOT_INFERRED_FROM_STATIC","native_new_star_not_claimed":True}
                continue
            star["source_JESTER_interpolated_static_radius_km_at_mass"] =float(np.interp(target,sm,sr))
            star["native_LAL_vs_original_JESTER_source_R_km"] =float(star["radius_km"]-star["source_JESTER_interpolated_static_radius_km_at_mass"])
            star["source_agreement_0p10km"] =bool(abs(star["native_LAL_vs_original_JESTER_source_R_km"])<.10)
            star["source_native_physics"] =source_physics_at_center(arrays,star["central_pressure_si_pa"],source_cs2)
            star["status"]="DIRECT_NATIVE_LAL_TOV_WITH_SOURCE_MR_CROSSCHECK" if star["source_agreement_0p10km"] else "SOURCE_NATIVE_LAL_MR_DISAGREEMENT_NOT_VALIDATED"
            report["results"][name]["stars"][key]=star
            report["targets_attempted_direct_native_LAL_TOV"].append([name,target,star["status"]])
        report["results"][name]["static_max_prior_mass_below_source_M_TOV_not_rotating"] = mass_prior_cdf(source_summary["native_mmax_msun"])
    ok=[r["stars"]["2.073"]["status"]=="DIRECT_NATIVE_LAL_TOV_WITH_SOURCE_MR_CROSSCHECK" for r in report["results"].values()]
    if not all(ok):
        report["status"]="PARTIAL_NATIVE_STATIC_TOV_ROOTS_OR_SOURCE_CROSSCHECK_FAILED"
    return report


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dir",type=Path,required=True)
    ap.add_argument("--fixture",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--nscan",type=int,default=64)
    args=ap.parse_args()
    import lal
    import lalsimulation
    fixture=json.loads(args.fixture.read_text())
    res=run(args.source_dir,fixture,lal,lalsimulation,nscan=args.nscan)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(res,sort_keys=True,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"status":res["status"],"EOS":len(res["results"]),
        "native_LAL_static_stars":len(res["targets_attempted_direct_native_LAL_TOV"]),
        "at_2p073":{name:r["stars"]["2.073"]["status"] for name,r in res["results"].items()}},sort_keys=True),flush=True)
    if res["status"]!="DIRECT_NATIVE_STATIC_TOV_ONLY_NOT_ROTATING_OR_EOS_POSTERIOR":
        raise SystemExit("F61 incomplete source-native 2.073 Msun roots; inspect JSON failure before claim")

if __name__=="__main__":main()