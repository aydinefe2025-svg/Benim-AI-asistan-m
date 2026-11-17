"""Pinned, directly solved C/GR rotating-star test for a *new* causal APR4 completion.

This is NOT the original (acausal) APR4 EOS, and does not establish an EOS
posterior or physical baryon-mass normalization. Failures are checkpointed.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys, traceback
from pathlib import Path
import numpy as np
from scipy.optimize import brentq

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parent/"rotating_gr"))
from native_lalsuite_apr4_causal_model import (
    NativeAPR4CausalEOS, reproduce_jester_export, tov, sha256,
    NPZ_SHA, LAL_TABLE_SHA, C, G
)
from precise_apr4_mass_spin_root import (
    run_model, solve_fixed_mf, TARGET_MASS_MSUN, TARGET_SPIN_HZ,
    MASS_TOL_MSUN, SPIN_TOL_HZ, RNS_COMMIT
)
from jester_to_rns import write_rns

def make_table(eos, mavg, dest, npoints, pmin):
    if not 30 <= npoints <= 200:
        raise ValueError("RNS table resolution must be 30..200")
    if not 0 < pmin <= eos.p0:
        raise ValueError("Use full native crust, including first source node")
    p=np.geomspace(pmin, eos.pcut*2.7, npoints)
    e=np.array([eos.energy(float(q)) for q in p])
    h=np.array([eos.h(float(q)) for q in p])
    n=(e+p)*np.exp(-h)/mavg
    rho=e*C*C/G*1e-3
    pcgs=p*C**4/G*10.0
    hcgs=h*(C*100)**2
    ncgs=n/1e6
    rows=np.column_stack((rho,pcgs,hcgs,ncgs))
    if not np.isfinite(rows).all() or (rows<=0).any():
        raise ValueError("Nonpositive/nonfinite EOS row")
    if not all(np.all(np.diff(rows[:,i])>0) for i in range(4)):
        raise ValueError("EOS density, pressure, H, or baryon proxy not monotone")
    # Secants are a necessary (not sufficient) causality check.
    sec=np.diff(p)/np.diff(e)
    if np.max(sec)>1+1e-8 or np.min(sec)<=0:
        raise ValueError(f"RNS input EOS secant causality failed: {sec.min()}, {sec.max()}")
    write_rns(dest,rows)
    return {"points":npoints,"p_min_geom_m-2":float(p[0]),
            "p_max_geom_m-2":float(p[-1]),"source_crust_included":True,
            "cs2_secant_min":float(sec.min()),"cs2_secant_max":float(sec.max()),
            "file_sha256":sha256(dest),"file_bytes":dest.stat().st_size,
            "baryon_proxy":"n=(epsilon+P)*exp(-h)/JESTER_mavg; NOT physical mu0 certification"}

def model_at(binary, table, ec, ratio):
    return run_model(binary,table,ec,ratio,timeout=180)

def root(binary,table,seed):
    return solve_fixed_mf(lambda ec,r:model_at(binary,table,ec,r),seed,max_iterations=18)

def run(args):
    out=args.out;out.parent.mkdir(parents=True,exist_ok=True)
    record={"schema":"J0740_APR4_NATIVE_CAUSAL_COMPLETION_RNS_GR_v1",
        "status":"IN_PROGRESS",
        "scientific_scope":"Causal-completed APR4 model, not original APR4",
        "original_APR4_globally_causal":False,
        "physical_baryon_mass_normalization":"NOT_ESTABLISHED",
        "rotating_branch_stability":"NOT_ESTABLISHED",
        "source_native_XPSI_EOS_Bayes":"NOT_RUN",
        "targets":{"mass_msun":TARGET_MASS_MSUN,"spin_hz":TARGET_SPIN_HZ,
                   "mass_tolerance_msun":MASS_TOL_MSUN,"spin_tolerance_hz":SPIN_TOL_HZ},
        "provenance":{"native_lal_table_expected_sha256":LAL_TABLE_SHA,
            "jester_npz_expected_sha256":NPZ_SHA,"rns_upstream_commit":RNS_COMMIT},
        "tables":{},"direct_RNS_models":[],"checks":{}}
    def checkpoint():
        out.write_text(json.dumps(record,sort_keys=True,indent=2,allow_nan=False,default=lambda x: x.item() if isinstance(x,np.generic) else (_ for _ in ()).throw(TypeError(type(x).__name__)))+"\n",encoding="utf-8")
    checkpoint()
    try:
        if sha256(args.native_table)!=LAL_TABLE_SHA:raise ValueError("native LAL 7.26.4 table SHA mismatch")
        if sha256(args.npz)!=NPZ_SHA:raise ValueError("JESTER source NPZ SHA mismatch")
        record["provenance"].update({"native_lal_table_actual_sha256":sha256(args.native_table),
            "jester_npz_actual_sha256":sha256(args.npz),
            "rns_binary_sha256":{b.name:sha256(b) for b in args.rns_binary}})
        eos=NativeAPR4CausalEOS(args.native_table)
        export=reproduce_jester_export(args.native_table,args.npz)
        if max(export["e_rel_max"],export["native_h_rel_max"])>1e-11 or export["dloge_abs_max"]>1e-10:
            raise ValueError("native JESTER export identity not reproduced")
        mavg=export["m_avg_geom_m"]
        if abs(eos.cs2(eos.pcut)-1)>1e-8:raise ValueError("causal cutoff mismatch")
        record["causal_cut_p_geom_m-2"]=eos.pcut
        record["jester_export_reproduction"]=export
        args.work.mkdir(parents=True,exist_ok=True)
        tables={}
        for pts in (196,200):
            path=args.work/f"APR4_causal_{pts}.rns"
            record["tables"][str(pts)]=make_table(eos,mavg,path,pts,eos.p0)
            tables[pts]=path
        checkpoint()
        # Independent nonrotating mass/radius target from the native causal EOS.
        lp=brentq(lambda x:tov(eos,math.exp(x))["M_msun"]-TARGET_MASS_MSUN,
                  math.log(eos.pcut*.10),math.log(eos.pcut*1.65))
        pc=math.exp(lp);static=tov(eos,pc)
        ec=eos.energy(pc)*C*C/G*1e-3
        record["native_static_target"]={**static,"ec_g_cm3":ec}
        checkpoint()
        # Test first: if even the static EOS transfer fails, don't mistake
        # a rotating-star root for a source-consistent result.
        for points,binary in [(196,args.rns_binary[0]),(196,args.rns_binary[1]),(200,args.rns_binary[1])]:
            entry={"kind":"static","table_points":points,"mesh":binary.name}
            record["direct_RNS_models"].append(entry)
            try:
                entry["result"]=model_at(binary,tables[points],ec,1.0)
                entry["delta_M_msun"]=entry["result"]["mass_msun"]-static["M_msun"]
                entry["delta_R_km"]=entry["result"]["radius_eq_km"]-static["R_km"]
                entry["pass"]=abs(entry["delta_M_msun"])<0.01 and abs(entry["delta_R_km"])<0.12
            except Exception as ex:
                entry.update({"pass":False,"error":f"{type(ex).__name__}: {ex}"})
            checkpoint()
        static_entries=[e for e in record["direct_RNS_models"] if e["kind"]=="static"]
        record["checks"]["static_MR_transfer_pass"]=all(e.get("pass",False) for e in static_entries)
        checkpoint()
        if not record["checks"]["static_MR_transfer_pass"]:
            raise RuntimeError("Static RNS vs native causal TOV transfer failed; rotation NOT_RUN")
        # Two independent seeds on each spatial mesh; same physical EOS.
        for binary in args.rns_binary:
            for seed in ((1.72,.986),(1.85,.986)):
                entry={"kind":"rotating_root","table_points":196,"mesh":binary.name,"seed":list(seed)}
                record["direct_RNS_models"].append(entry)
                try:
                    ans=root(binary,tables[196],seed)
                    entry.update({"status":"PASS_DIRECT_C_GR_ROOT","result":ans})
                except Exception as ex:
                    entry.update({"status":"FAILED","error":f"{type(ex).__name__}: {ex}",
                        "trace":getattr(ex,"trace",[])})
                checkpoint()
        # One independent EOS discretization check at fine spatial mesh.
        entry={"kind":"rotating_root","table_points":200,
               "mesh":args.rns_binary[1].name,"seed":[1.72,.986]}
        record["direct_RNS_models"].append(entry)
        try:
            entry.update({"status":"PASS_DIRECT_C_GR_ROOT",
                          "result":root(args.rns_binary[1],tables[200],(1.72,.986))})
        except Exception as ex:
            entry.update({"status":"FAILED","error":f"{type(ex).__name__}: {ex}",
                          "trace":getattr(ex,"trace",[])})
        checkpoint()
        roots=[x for x in record["direct_RNS_models"] if x["kind"]=="rotating_root"]
        if len(roots)!=5 or not all(x["status"]=="PASS_DIRECT_C_GR_ROOT" for x in roots):
            raise RuntimeError("At least one direct RNS mass-spin root failed")
        coarse=[x["result"] for x in roots if x["mesh"]==args.rns_binary[0].name]
        fine=[x["result"] for x in roots if x["mesh"]==args.rns_binary[1].name and x["table_points"]==196]
        alt=[x["result"] for x in roots if x["mesh"]==args.rns_binary[1].name and x["table_points"]==200]
        assert len(coarse)==len(fine)==2 and len(alt)==1
        record["checks"].update({
            "coarse_independent_seeds_delta_R_km":abs(coarse[0]["radius_eq_km"]-coarse[1]["radius_eq_km"]),
            "fine_independent_seeds_delta_R_km":abs(fine[0]["radius_eq_km"]-fine[1]["radius_eq_km"]),
            "spatial_mesh_delta_R_km":abs(coarse[0]["radius_eq_km"]-fine[0]["radius_eq_km"]),
            "EOS_196_vs_200_delta_R_km":abs(fine[0]["radius_eq_km"]-alt[0]["radius_eq_km"]),
            "all_M_f_tolerances":all(abs(x["result"]["mass_msun"]-TARGET_MASS_MSUN)<=MASS_TOL_MSUN and
                abs(x["result"]["spin_hz"]-TARGET_SPIN_HZ)<=SPIN_TOL_HZ for x in roots)})
        record["checks"]["numerical_convergence_pass"]=(
            record["checks"]["all_M_f_tolerances"] and
            record["checks"]["coarse_independent_seeds_delta_R_km"]<.002 and
            record["checks"]["fine_independent_seeds_delta_R_km"]<.002 and
            record["checks"]["spatial_mesh_delta_R_km"]<.03 and
            record["checks"]["EOS_196_vs_200_delta_R_km"]<.03)
        if not record["checks"]["numerical_convergence_pass"]:
            raise RuntimeError("Rotating C/GR resolution or root tolerance gate failed")
        record["status"]="PASS_CONDITIONAL_CAUSAL_APR4_ROTATING_C_GR"
        record["conditional_rotating_equatorial_radius_km"]=fine[0]["radius_eq_km"]
        record["warnings"]=["New explicit causal completion, not the original APR4 table",
          "JESTER mavg baryon normalization is conditional, not physical mu0",
          "Turning-point and secular rotating-branch stability not established",
          "No X-PSI nuisance-marginalized EOS Bayes factor"]
        checkpoint()
        return record
    except Exception as ex:
        record["status"]="FAILED_OR_PARTIAL; NO_PHYSICAL_CLAIM"
        record["failure"]=f"{type(ex).__name__}: {ex}"
        record["traceback"]=traceback.format_exc(limit=5)
        checkpoint()
        return record

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--native-table",type=Path,required=True)
    ap.add_argument("--npz",type=Path,required=True)
    ap.add_argument("--rns-binary",type=Path,nargs=2,required=True)
    ap.add_argument("--work",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    result=run(a)
    print(json.dumps({"status":result["status"],"checks":result["checks"],
                      "failure":result.get("failure"),
                      "conditional_rotating_equatorial_radius_km":result.get("conditional_rotating_equatorial_radius_km")},
                     indent=2))
    if result["status"]!="PASS_CONDITIONAL_CAUSAL_APR4_ROTATING_C_GR":
        raise SystemExit(1)
if __name__=="__main__":main()
