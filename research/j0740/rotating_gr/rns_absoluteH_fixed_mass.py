"""Source absolute-H and EOS-matched surface C solver, solve actual fixed M.

A validated mass-root here means *numerical* fixed-gravitational-mass
consistency on this modified C surface-boundary experiment, NOT physically
validated crust or NICER/XMM EOS Bayesian evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from resilient_mass_root import resilient_mass_root, NumericalRootError
from rns_benchmark import run_rns, OBSERVED_SPIN_HZ
from axis_ratio_rns import run_rns_at_spin_with_ratio_fallback
from seven_eos_sequence import stable_source_radius_at_mass
from jester_to_rns import from_jester_npz,write_rns
from j0740_absolute_enthalpy_gr import absolute_pseudoenthalpy_rows

EOS=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")
TARGET=2.073
RNS="97e85d325a33e37f702306414533f6cd77812477"
SOURCE="e6768650ce992abfd1153a6833857572fe5cd230"
SHA_PRIOR="d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"


def solve_near_center(evaluate, rho0:float, target:float=TARGET, tol:float=0.0015):
    """Seed with the actually measured model; find nearest stable M crossing."""
    if not math.isfinite(rho0) or rho0<=0 or not math.isfinite(target):
        raise ValueError("invalid root center or target")
    attempts=[]
    def checked(rho):
        try:
            model=evaluate(rho)
            mass=float(model["mass_msun"])
            radius=float(model["radius_eq_km"])
            if not(math.isfinite(mass) and math.isfinite(radius) and .5<mass<3.5 and 6<radius<30):
                raise ValueError("Nonphysical model")
            attempts.append({"rho":rho,"M":mass,"R":radius,"status":"OK"})
            return model
        except (RuntimeError,ValueError,TimeoutError) as exc:
            attempts.append({"rho":rho,"status":"REJECTED","error":str(exc)[:500]})
            return None
    center=checked(rho0)
    if center is None:
        raise NumericalRootError("Original center failed with corrected H source surface",trace=attempts)
    m0=float(center["mass_msun"])
    if abs(m0-target)<=tol:
        return center,{"method":"original center within printed solver precision","pre_root_scan":attempts,"root_trace":[]}
    if m0>target:
        grid=(.99,.98,.96,.93,.90,.85,.80,.75)
        pairs=[]
        for r in grid:
            lower=checked(rho0*r)
            if lower is not None and float(lower["mass_msun"])<target:
                pairs=[rho0*r,rho0]
                break
    else:
        grid=(1.01,1.02,1.04,1.07,1.10,1.15,1.20,1.25)
        pairs=[]
        for r in grid:
            upper=checked(rho0*r)
            if upper is not None and float(upper["mass_msun"])>target:
                pairs=[rho0,rho0*r]
                break
    if not pairs:
        raise NumericalRootError("No physically bracketed near-center increasing-mass root",trace=attempts)
    # Existing fail-closed certified mass solver rejects nonmonotonic/failing points.
    root,trace=resilient_mass_root(evaluate,target,*pairs,tolerance=tol)
    if abs(float(root["mass_msun"])-target)>tol:
        raise NumericalRootError("Certified root mass outside requested tolerance",trace=trace)
    return root,{"method":"validated increasing-M bracket and resilient root",
                 "bracket_g_cm3":pairs,"pre_root_scan":attempts,"root_trace":trace}


def audit(prior,binpath:Path,source_dir:Path,outdir:Path):
    if (prior.get("status")!="ALL_SEVEN_VALIDATED" or
        prior.get("jester_upstream_commit")!=SOURCE or
        prior.get("rns_upstream_commit")!=RNS or
        set(prior.get("eos",{}))!=set(EOS)):
        raise ValueError("Prior original seven-EOS GR evidence mismatch")
    report={}
    for name in EOS:
        old=prior["eos"][name]
        try:
            src=source_dir/(name+".npz")
            sha=hashlib.sha256(src.read_bytes()).hexdigest()
            if sha!=old["source_npz_sha256"]:
                raise ValueError("Pinned JESTER original NPZ SHA mismatch")
            legacy,meta=from_jester_npz(src,points=196)
            corrected=absolute_pseudoenthalpy_rows(
                legacy,meta["jester_lowest_pressure_enthalpy_offset"])
            path=outdir/(name+"_absoluteH_sourceSurface_fixedM.rns")
            write_rns(path,corrected)
            rotating,rt=solve_near_center(
                lambda rho:run_rns_at_spin_with_ratio_fallback(
                    binpath,path,central_density=rho,spin_hz=OBSERVED_SPIN_HZ),
                float(old["rns_rotating_at_target"]["central_energy_density_g_cm3"]))
            static,st=solve_near_center(
                lambda rho:run_rns(binpath,path,central_density=rho,spin_hz=0.0,timeout=70),
                float(old["rns_static_at_same_gravitational_mass"]["central_energy_density_g_cm3"]))
            reference,branch=stable_source_radius_at_mass(src,float(static["mass_msun"]))
            delta=float(static["radius_eq_km"])-reference
            if abs(delta)>0.25:
                status="FIXED_MASS_COMPUTED_BUT_INDEPENDENT_SOURCE_TOV_MISMATCH"
            else:status="FIXED_MASS_AND_SOURCE_TOV_SCREEN_PASS"
            report[name]={
                "status":status,"source_npz_sha256":sha,
                "source_pseudoenthalpy_origin":meta["jester_lowest_pressure_enthalpy_offset"],
                "RNS_source_absolute_H_EOS_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                "rotating":rotating,"static":static,
                "rotation_minus_static_eq_R_at_fixed_M_km":round(float(rotating["radius_eq_km"])-float(static["radius_eq_km"]),5),
                "original_rotating_eq_R_km":old["rns_rotating_at_target"]["radius_eq_km"],
                "corrected_minus_original_rotating_R_at_fixed_M_km":round(float(rotating["radius_eq_km"])-float(old["rns_rotating_at_target"]["radius_eq_km"]),5),
                "JESTER_original_static_TOV_R_km":reference,
                "static_RNS_minus_JESTER_static_TOV_km":delta,
                "source_stable_TOV_branch":branch,
                "rotating_mass_root":rt,"static_mass_root":st}
        except Exception as e:
            report[name]={"status":"FIXED_MASS_OR_TOV_FAILED","error_type":type(e).__name__,
                          "reason":str(e)[:900]}
            if isinstance(e,NumericalRootError):report[name]["failed_trace"]=e.trace
        print(name,report[name]["status"],flush=True)
    passes=sum(v["status"]=="FIXED_MASS_AND_SOURCE_TOV_SCREEN_PASS" for v in report.values())
    return {"schema":"j0740-absoluteH-source-surface-corrected-fixed-gravitational-mass-v1",
            "status":"SEVEN_NUMERICAL_FIXED_MASS_AND_STATIC_TOV_SCREEN_PASS" if passes==7 else "INCOMPLETE_FIXED_MASS_OR_STATIC_TOV_REVIEW",
            "passed":passes,"required":7,
            "target_M_msun":TARGET,"target_f_hz":OBSERVED_SPIN_HZ,
            "rns_C_patch_scope":"only MakeSphere Hmin E_surface P_surface changed to first JESTER EOS table knot; original GR RNS code remains untouched",
            "caveats":["Real full GR but patched surface truncates at JESTER first EOS node; missing low-pressure crust remains a physics issue",
                       "Causality tests still indicate 6 crust negative sound-speed and 3 central >c",
                       "Mass tolerance 0.0015 M_sun and 0.01 km stdout RNS radius resolution",
                       "Not X-PSI photon likelihood or normalized EOS posterior"],"eos":report}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--original-GR",type=Path,required=True)
    p.add_argument("--binary",type=Path,required=True)
    p.add_argument("--jester-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    data=a.original_GR.read_bytes()
    if hashlib.sha256(data).hexdigest()!=SHA_PRIOR:raise ValueError("original full GR JSON SHA mismatch")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    ans=audit(json.loads(data),a.binary,a.jester_dir,a.out.parent)
    a.out.write_text(json.dumps(ans,indent=2,sort_keys=True)+"\n")
    if ans["passed"]!=7:raise SystemExit("Evidence retained: not all seven fixed-M corrected H models validated against independent source TOV")


if __name__=="__main__":main()
