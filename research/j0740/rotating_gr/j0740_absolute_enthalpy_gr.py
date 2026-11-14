"""Correct the JESTER->RNS pseudoenthalpy *origin*, then stress actual C/RNS GR.

JESTER's `h` comes from LALSimulation pseudoenthalpy H(P)/c^2, measured
from zero pressure, NOT from the lower cutoff P_min. RNS manual requires
H(P)=c^2∫_0^P dP/(epsilon+P), in cm^2/s^2.

The historical J0740 converter incorrectly used (h-h[0])*c^2 + 1;
this introduces an artificial 1 -> 5e16 jump in log H and catastrophically
ill-conditions RNS's p_at_h interpolation. Old 7/7 GR evidence is retained;
this study uses the same original EOS NPZ and same central densities only.
No 12.9GB Salmi photon archive or X-PSI nuisance likelihood is accessed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np

C2_CGS=(29979245800.0)**2
EOS=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")
JESTER_SHA="e6768650ce992abfd1153a6833857572fe5cd230"
RNS_SHA="97e85d325a33e37f702306414533f6cd77812477"
PRIOR_JSON_SHA="d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"


def absolute_pseudoenthalpy_rows(legacy_rows:np.ndarray, source_h_min:float)->np.ndarray:
    """Keep all P, e, n and dH unchanged; restore nonzero H(P_min)=h_min*c²."""
    a=np.asarray(legacy_rows,dtype=float)
    if (a.ndim!=2 or a.shape[1]!=4 or len(a)<30
            or not np.all(np.isfinite(a)) or np.any(a<=0)
            or not all(np.all(np.diff(a[:,j])>0) for j in range(4))
            or not math.isfinite(source_h_min) or source_h_min<=0
            or not math.isclose(float(a[0,2]),1.0,rel_tol=1e-12,abs_tol=1e-12)):
        raise ValueError("Expected positive original JESTER pseudoenthalpy and legacy H(Pmin)=1; refused")
    out=a.copy()
    out[:,2]=a[:,2]-1.0+source_h_min*C2_CGS
    if not np.all(np.isfinite(out)) or np.any(np.diff(out[:,2])<=0):
        raise ValueError("Restored enthalpy not strictly monotone")
    if not math.isclose(float(out[0,2]),source_h_min*C2_CGS,rel_tol=1e-14):
        raise ValueError("Source absolute pseudoenthalpy lower boundary differs")
    if not np.array_equal(a[:,[0,1,3]],out[:,[0,1,3]]):
        raise ValueError("Energy, pressure or number density changed unexpectedly")
    return out


def compare_at_same_center(old:dict,corrected:dict)->dict:
    keys=("mass_msun","radius_eq_km","central_energy_density_g_cm3")
    if any(k not in old or k not in corrected for k in keys):
        raise ValueError("Missing C/GR stellar mass-radius model")
    values=[float(x[k]) for x in (old,corrected) for k in keys]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Nonfinite stellar model")
    if not math.isclose(float(old["central_energy_density_g_cm3"]),
                        float(corrected["central_energy_density_g_cm3"]),rel_tol=5e-6):
        raise ValueError("Cannot compare different central densities")
    return {"prior_gr_mass_msun":float(old["mass_msun"]),
            "corrected_gr_mass_msun":float(corrected["mass_msun"]),
            "delta_gr_mass_msun":float(corrected["mass_msun"]-old["mass_msun"]),
            "prior_gr_radius_eq_km":float(old["radius_eq_km"]),
            "corrected_gr_radius_eq_km":float(corrected["radius_eq_km"]),
            "delta_gr_radius_eq_km":float(corrected["radius_eq_km"]-old["radius_eq_km"]),
            "same_central_density_g_cm3":float(old["central_energy_density_g_cm3"]),
            "warning":"Fixed central density, NOT same gravitational or baryonic mass. Not normalized EOS Bayesian evidence."}


def audit(prior:dict,rns_bin:Path,jester_dir:Path,outdir:Path)->dict:
    if (prior.get("status")!="ALL_SEVEN_VALIDATED" or prior.get("validated_eos_count")!=7
            or prior.get("jester_upstream_commit")!=JESTER_SHA
            or prior.get("rns_upstream_commit")!=RNS_SHA
            or set(prior.get("eos",{}))!=set(EOS)):
        raise ValueError("Original successful seven-EOS GR identity mismatch")
    from jester_to_rns import from_jester_npz,write_rns
    from rns_benchmark import run_rns,OBSERVED_SPIN_HZ,RNS_COMMIT
    from axis_ratio_rns import run_rns_at_spin_with_ratio_fallback
    from rns_three_path_consistency import table_profile
    if RNS_COMMIT != RNS_SHA:
        raise ValueError("Pinned C solver commit identity changed")
    models={}
    for name in EOS:
        record=prior["eos"][name]
        try:
            src=jester_dir/(name+".npz")
            source_sha=hashlib.sha256(src.read_bytes()).hexdigest()
            if source_sha!=record["source_npz_sha256"]:
                raise ValueError("Original JESTER NPZ SHA mismatch")
            oldrows,meta=from_jester_npz(src,points=196)
            h0=float(meta["jester_lowest_pressure_enthalpy_offset"])
            goodrows=absolute_pseudoenthalpy_rows(oldrows,h0)
            p_old=outdir/(name+"_legacy_H.rns")
            p_new=outdir/(name+"_absolute_H.rns")
            write_rns(p_old,oldrows)
            write_rns(p_new,goodrows)
            rho_rot=float(record["rns_rotating_at_target"]["central_energy_density_g_cm3"])
            rho_static=float(record["rns_static_at_same_gravitational_mass"]["central_energy_density_g_cm3"])
            oldprof=table_profile(oldrows,rho_rot)
            newprof=table_profile(goodrows,rho_rot)
            # Actual pinned C/RNS solver, new table and exactly prior model centers.
            rot=run_rns_at_spin_with_ratio_fallback(rns_bin,p_new,
                      central_density=rho_rot,spin_hz=OBSERVED_SPIN_HZ)
            sta=run_rns(rns_bin,p_new,central_density=rho_static,spin_hz=0.)
            models[name]={
                "status":"FULL_GR_CORRECTED_H_FIXED_CENTER_COMPUTED",
                "original_jester_npz_sha256":source_sha,
                "historical_legacy_eos_text_sha256":record["rns_table_sha256"],
                "legacy_eos_text_sha256_regenerated":hashlib.sha256(p_old.read_bytes()).hexdigest(),
                "corrected_eos_text_sha256":hashlib.sha256(p_new.read_bytes()).hexdigest(),
                "h_min_source_dimensionless":h0,
                "legacy_h_min_cgs":float(oldrows[0,2]),
                "corrected_h_min_cgs":float(goodrows[0,2]),
                "old_profile_max_p_at_h_roundtrip_rel_error":oldprof["max_p_at_h_roundtrip_relative_error"],
                "corrected_profile_max_p_at_h_roundtrip_rel_error":newprof["max_p_at_h_roundtrip_relative_error"],
                "old_profile_negative_h_at_p_slopes":oldprof["h_at_p_negative_dlogh_dlogp_count"],
                "corrected_profile_negative_h_at_p_slopes":newprof["h_at_p_negative_dlogh_dlogp_count"],
                "rotating_model_fixed_original_central_density":rot,
                "static_model_fixed_original_central_density":sta,
                "rotating_original_GR_vs_corrected_H":compare_at_same_center(record["rns_rotating_at_target"],rot),
                "static_original_GR_vs_corrected_H":compare_at_same_center(record["rns_static_at_same_gravitational_mass"],sta),
            }
        except Exception as exc:
            models[name]={"status":"CORRECTED_H_GR_NUMERICAL_FAILURE","error_type":type(exc).__name__,"message":str(exc)[:900]}
        print(name,models[name]["status"],flush=True)
    n=sum(v["status"]=="FULL_GR_CORRECTED_H_FIXED_CENTER_COMPUTED" for v in models.values())
    return {"schema":"j0740-absolute-pseudoenthalpy-seven-eos-GR-v1",
            "status":"ALL_SEVEN_RECORRECTED_GR_FIXED_CENTER_COMPUTED" if n==7 else "PARTIAL_CORRECTED_H_GR_NOT_FINAL",
            "successful_stars_rotating_and_static":n*2,
            "required_stars":14,
            "source_JESTER_commit":JESTER_SHA,"source_RNS_C_commit":RNS_SHA,
            "original_GR_run":42353019033,"original_GR_json_sha256":PRIOR_JSON_SHA,
            "scientific_correction":"Preserves LALSimulation pseudoenthalpy absolute H(P)=h(P)*c^2; no artificial subtraction of h(P_min). RNS wants enthalpy integral from P=0.",
            "limitations":["Models compared at same central density, not fixed gravitational mass",
                           "New corrected H fixed-target-M and static TOV comparison still needed",
                           "Crust negative c_s^2 and ENG/WFF superluminal physical prior gates remain",
                           "No full 15D X-PSI NICER/XMM photon likelihood or EOS evidence"],
            "eos":models}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rns-json",required=True,type=Path)
    parser.add_argument("--binary",required=True,type=Path)
    parser.add_argument("--jester-dir",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args()
    original=args.rns_json.read_bytes()
    if hashlib.sha256(original).hexdigest()!=PRIOR_JSON_SHA:
        raise ValueError("Historical original GR JSON byte identity mismatch")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    result=audit(json.loads(original),args.binary,args.jester_dir,args.out.parent)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    if result["successful_stars_rotating_and_static"]!=14:
        raise SystemExit("Partial corrected H RNS model evaluation retained; review evidence JSON")

if __name__=="__main__":main()
