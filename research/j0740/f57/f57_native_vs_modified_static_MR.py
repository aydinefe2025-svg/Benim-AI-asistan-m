"""F57 independent native-JESTER versus lifted-F42 WFF1 STATIC R(M=2.073) audit.

Do NOT confuse existing JESTER native static M-R with newly computed RNS
stars, and do NOT interpret original source WFF1 in the acausal domain
as physically validated. No source-native rotating star is computed here.
This fills a distinct missing source-output comparison beyond F56's
pressure-aligned EOS identity audit and preserves all original data.
"""
from __future__ import annotations

import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator

JESTER_WFF1_SHA = "119b8a25435faeddf00f5d3638f3ff2ff00283ce60caacc24cc37c6e2e030ed3"
F42_ZIP_SHA = "c8d8cdc9804a702860ab1af65b60fa25dfac0f74fce9ec6347c4271ea3353115"
WFF1_F42_TABLE_SHA = "0ac47df0d250baef55c2b046a809ed433215a31332b268177babf667e306f02f"
JESTER_PINNED_COMMIT = "e6768650ce992abfd1153a6833857572fe5cd230"
TARGET_M = 2.073
INTERP_TOL_KM = 0.025


def sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def stable_native_radius(mass, radius, target=TARGET_M):
    """Interpolate only ONE locally monotonically rising actual source-TOV mass branch."""
    m=np.asarray(mass,dtype=float)
    r=np.asarray(radius,dtype=float)
    if (m.ndim!=1 or r.shape!=m.shape or len(m)<50 or
        not (np.isfinite(m).all() and np.isfinite(r).all()) or
        np.any(m<=0) or np.any(r<5) or np.any(r>30) or
        not math.isfinite(target)):
        raise ValueError("BAD_JESTER_NATIVE_TOV_MR_ARRAY_OR_RADIUS_UNITS")
    peak=int(np.argmax(m))
    hits=[i for i in range(peak) if m[i]<target<=m[i+1]]
    if len(hits)!=1:
        raise ValueError("NO_UNIQUE_NATIVE_RISING_MASS_CROSSING")
    i=hits[0]
    lo,hi=max(0,i-5),min(peak+1,i+7)
    local_m=m[lo:hi]
    local_r=r[lo:hi]
    if len(local_m)<6 or np.any(np.diff(local_m)<=0):
        raise ValueError("LOCAL_SOURCE_TOV_NONMONOTONIC_BEFORE_TARGET")
    if not m[i]<target<m[i+1]:
        raise ValueError("SOURCE_TARGET_ENDPOINT_NOT_INTERIOR")
    Rlinear=float(np.interp(target,m[i:i+2],r[i:i+2]))
    Rpchip=float(PchipInterpolator(local_m,local_r,extrapolate=False)(target))
    interp_gap=abs(Rpchip-Rlinear)
    return {
        "source_native_TOV_existing_not_new":True,
        "target_mass_msun":target,
        "linear_local_native_radius_km":Rlinear,
        "pchip_local_native_radius_km":Rpchip,
        "pchip_minus_linear_interpolation_km":Rpchip-Rlinear,
        "interpolation_method_spread_km":interp_gap,
        "source_existing_TOV_points":len(m),
        "native_mass_peak_sample_index":peak,
        "native_mass_peak_sample_msun":float(m[peak]),
        "native_peak_at_last_sample_not_global_max_proof":peak==len(m)-1,
        "matched_bracket_index":i,
        "source_native_bracket":[
            {"mass_msun":float(m[j]),"radius_km":float(r[j])} for j in (i,i+1)],
        "physical_source_EOS_causality_certified":False,
    }


def run(npz,f43,out):
    if sha256(npz)!=JESTER_WFF1_SHA:
        raise ValueError("JESTER_ORIGINAL_WFF1_SHA256_MISMATCH")
    source=json.loads(Path(f43).read_text())
    if source.get("source_F42_artifact_sha256")!=F42_ZIP_SHA:
        raise ValueError("F43_F42_SOURCE_ZIP_SHA_MISMATCH")
    entry=source.get("eos",{}).get("WFF1",{})
    if entry.get("source_rns_sha256")!=WFF1_F42_TABLE_SHA:
        raise ValueError("F43_SOURCE_WFF1_CANDIDATE_TABLE_SHA_DRIFT")
    candidate=entry["first_stable_2p073_root"]["fine"]
    if abs(float(candidate["mass_msun"])-TARGET_M)>1e-5:
        raise ValueError("F43_2P073_STATIC_TOV_ROOT_NO_LONGER_MATCHES")
    if candidate.get("tov_spherical")!="STATIC_ONLY_NOT_ROTATING":
        raise ValueError("F43_STATIC_TOV_MISLABELED_AS_ROTATING")
    with np.load(npz,allow_pickle=False) as z:
        native=stable_native_radius(z["masses_EOS"],z["radii_EOS"])
        cs2=np.asarray(z["cs2"],float)
        energy=np.asarray(z["e"],float)
        if cs2.ndim!=1 or cs2.shape!=energy.shape or not np.isfinite(cs2).all():
            raise ValueError("NATIVE_CS2_OR_ENERGY_GRID_DRIFT")
    nonpos=int(np.count_nonzero(cs2<=0))
    superlum=int(np.count_nonzero(cs2>1+1e-8))
    if nonpos<1 or superlum<1:
        raise ValueError("EXPECTED_ORIGINAL_NATIVE_WFF1_CAUSALITY_FAILURE_ABSENT")
    delta=float(candidate["radius_km"])-native["pchip_local_native_radius_km"]
    spread=native["interpolation_method_spread_km"]
    result={
        "schema":"J0740_F57_WFF1_SOURCE_NATIVE_STATIC_VS_NEW_F42_CANDIDATE_MR_V1",
        "status":("STATIC_SOURCE_RADIUS_COMPARISON_PASS_NOT_PHYSICAL_EOS"
                  if spread<=INTERP_TOL_KM else "STATIC_SOURCE_INTERPOLATION_SPREAD_NEEDS_CHECK"),
        "native_npz_source_commit":JESTER_PINNED_COMMIT,
        "native_npz_sha256":sha256(npz),
        "F43_report_sha256":sha256(f43),
        "F43_F42_original_candidate_artifact_sha256":F42_ZIP_SHA,
        "F43_WFF1_lifted_table_sha256":WFF1_F42_TABLE_SHA,
        "native_causality":{
            "max_native_cs2_over_c2":float(np.max(cs2)),
            "nonpositive_nodes":nonpos,
            "superluminal_nodes":superlum,
            "native_source_globally_physical":"FAIL_SAMPLED_CAUSALITY"},
        "JESTER_native_existing_static_TOV_MR":native,
        "F43_lifted_candidate_independently_integrated_static_TOV":{
            "target_mass_msun":float(candidate["mass_msun"]),
            "radius_km":float(candidate["radius_km"]),
            "center_density_g_cm3":float(candidate["center_density_g_cm3"]),
            "TOV_not_rotating":True,
            "new_candidate_not_original_nuclear_WFF1":True},
        "lifted_minus_native_static_radius_at_M2p073_km":delta,
        "source_MR_radius_comparison_interpolation_tolerance_km":INTERP_TOL_KM,
        "native_static_interpolation_is_not_new_GR_solve":True,
        "F43_lifted_candidate_TOV_is_not_original_source_EOS":True,
        "native_source_max_sampled_mass_not_global_stable_max":True,
        "no_fresh_RNS_C_run":True,
        "native_EOS_full_physical_acceptance":"NOT_ESTABLISHED",
        "global_rotating_dynamical_stability":"NOT_ESTABLISHED",
        "native_XPSI_photon_level_7EOS_Bayes":"NOT_RUN",
        "interpretation":"A cross-model comparison of existing independently produced static M-R products at equal gravitational mass; the source-native model carries sampled acausal/high-density flaws, and its source M-R samples are not recomputed. Neither source model validated as original physical WFF1 star at J0740 spin.",
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,sort_keys=True,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:result[k] for k in ("status","lifted_minus_native_static_radius_at_M2p073_km","native_causality")},sort_keys=True),flush=True)
    return result


def main():
    p=argparse.ArgumentParser()
    for k in ("npz","f43","out"):p.add_argument("--"+k,required=True,type=Path)
    a=p.parse_args()
    result=run(a.npz,a.f43,a.out)
    if result["status"]!="STATIC_SOURCE_RADIUS_COMPARISON_PASS_NOT_PHYSICAL_EOS":
        raise SystemExit(2)


if __name__=="__main__":main()
