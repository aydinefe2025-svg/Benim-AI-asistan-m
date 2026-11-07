"""Diagnose absolute-JESTER-H mismatch against fixed RNS C stellar surface boundaries.

Two isolated builds of the pinned RNS C solver: (1) only Hmin from EOS
table, (2) Hmin plus Psurface and Esurface from that same EOS table.
All results are DIAGNOSTIC ONLY. They are NOT a new EOS posterior or
a validated physical star model without full outer-crust/likelihood checks.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
EOS=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")
RNS_SHA="97e85d325a33e37f702306414533f6cd77812477"
JESTER_SHA="e6768650ce992abfd1153a6833857572fe5cd230"
PRIOR_SHA="d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"
PATCH={
 "hmin":[("star->enthalpy_min=1.0/(C*C);","star->enthalpy_min=pow(10.0,eos->log_h_tab[1]);")],
 "hmin_surface":[
  ("star->enthalpy_min=1.0/(C*C);","star->enthalpy_min=pow(10.0,eos->log_h_tab[1]);"),
  ("star->e_surface=7.8*C*C*KSCALE;","star->e_surface=pow(10.0,eos->log_e_tab[1]);"),
  ("p_surface=1.01e8*KSCALE;","p_surface=pow(10.0,eos->log_p_tab[1]);")
 ]}

def patch_source(source:str,mode:str)->str:
    if mode not in PATCH:raise ValueError("Unknown patch")
    for before,after in PATCH[mode]:
        if source.count(before)!=1:raise ValueError("Original pinned C anchor not unique")
        source=source.replace(before,after)
    return source

def attempt(binary:Path,eos:Path,rho:float,spin:float):
    from rns_benchmark import run_rns
    from axis_ratio_rns import run_rns_at_spin_with_ratio_fallback
    try:
        r=(run_rns(binary,eos,central_density=rho,spin_hz=0,timeout=70)
          if spin==0 else run_rns_at_spin_with_ratio_fallback(binary,eos,central_density=rho,spin_hz=spin))
        return {"status":"FINITE_C_GR_MODEL","mass_msun":r["mass_msun"],
                "radius_eq_km":r["radius_eq_km"],"spin_hz":r["spin_hz_reported"]}
    except Exception as e:
        return {"status":"C_GR_NUMERICAL_FAILURE","error_type":type(e).__name__,"error":str(e)[:950]}

def audit(original, binaries, jester_dir:Path,outdir:Path):
    from jester_to_rns import from_jester_npz,write_rns
    from j0740_absolute_enthalpy_gr import absolute_pseudoenthalpy_rows
    from rns_benchmark import OBSERVED_SPIN_HZ
    if original.get("status")!="ALL_SEVEN_VALIDATED" or original.get("jester_upstream_commit")!=JESTER_SHA or original.get("rns_upstream_commit")!=RNS_SHA or set(original.get("eos",{}))!=set(EOS) or set(binaries)!=set(PATCH):
        raise ValueError("Pinned prior/source C identity mismatch")
    out={}
    for name in EOS:
        old=original["eos"][name];src=jester_dir/(name+".npz")
        if hashlib.sha256(src.read_bytes()).hexdigest()!=old["source_npz_sha256"]:
            raise ValueError("Original NPZ changed")
        rows,meta=from_jester_npz(src,points=196)
        rows=absolute_pseudoenthalpy_rows(rows,meta["jester_lowest_pressure_enthalpy_offset"])
        path=outdir/(name+"_absoluteH.rns");write_rns(path,rows)
        static_rho=float(old["rns_static_at_same_gravitational_mass"]["central_energy_density_g_cm3"])
        rot_rho=float(old["rns_rotating_at_target"]["central_energy_density_g_cm3"])
        modes={}
        for mode,binary in binaries.items():
            sta=attempt(binary,path,static_rho,0.0)
            rot=attempt(binary,path,rot_rho,float(OBSERVED_SPIN_HZ)) if sta["status"]=="FINITE_C_GR_MODEL" else {"status":"NOT_ATTEMPTED_STATIC_FAILURE"}
            modes[mode]={"static":sta,"rotating":rot}
        out[name]={"source_npz_sha256":old["source_npz_sha256"],
                   "source_h_min":meta["jester_lowest_pressure_enthalpy_offset"],
                   "absolute_h_table_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                   "modes":modes}
        print(name,[(m,v["static"]["status"],v["rotating"]["status"]) for m,v in modes.items()],flush=True)
    return {"status":"DIAGNOSTIC_RNS_SURFACE_BOUNDARY_CHECK_NOT_EOS_VALIDATION",
            "schema":"j0740-boundary-source-absoluteH-v1",
            "rns_commit":RNS_SHA,"jester_commit":JESTER_SHA,
            "original_7EOS_GR_run":42353019033,
            "limitation":"C variants change surface integration cutoff and require independent EOS/crust and TOV validation. No Bayes evidence.",
            "eos":out}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--patch",choices=PATCH)
    p.add_argument("--original-c",type=Path)
    p.add_argument("--patched-c",type=Path)
    p.add_argument("--rns-json",type=Path)
    p.add_argument("--source-dir",type=Path)
    p.add_argument("--hmin-binary",type=Path)
    p.add_argument("--surface-binary",type=Path)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.patch:
        if not a.original_c or not a.patched_c:p.error("patch needs C paths")
        orig=a.original_c.read_text()
        new=patch_source(orig,a.patch)
        a.patched_c.write_text(new)
        print(a.patch,hashlib.sha256(orig.encode()).hexdigest(),hashlib.sha256(new.encode()).hexdigest())
        return
    if not all((a.rns_json,a.source_dir,a.hmin_binary,a.surface_binary,a.out)):
        p.error("Missing required evidence and binary paths")
    raw=a.rns_json.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PRIOR_SHA:
        raise ValueError("Original 7/7 GR data SHA mismatch")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    output=audit(json.loads(raw),{"hmin":a.hmin_binary,"hmin_surface":a.surface_binary},a.source_dir,a.out.parent)
    a.out.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")

if __name__=="__main__":main()
