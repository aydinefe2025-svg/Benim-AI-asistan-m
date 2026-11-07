"""196-point RNS EOS table derivative vs exact JESTER native cs2 at J0740.

Source identity checks reproduce the *same* 196 row RNS EOS file SHA256
used for the actual 7/7 GR run. This compares local table secant and local
log-power-law derivative to the pinned source native cs2; neither is a new
run of RNS or an exact proof of its internal interpolation derivative.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from jester_to_rns import from_jester_npz,write_rns

EOS=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")
SOURCE_COMMIT="e6768650ce992abfd1153a6833857572fe5cd230"
RNS_JSON_SHA256="d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"
C_CGS=2.99792458e10


def eos_table_slopes(rows:np.ndarray, center_rho:float)->dict:
    rows=np.asarray(rows,dtype=float)
    if (rows.ndim!=2 or rows.shape[1]!=4 or len(rows)<30 or len(rows)>200
            or not np.all(np.isfinite(rows)) or np.any(rows<=0)
            or np.any(np.diff(rows[:,0])<=0) or np.any(np.diff(rows[:,1])<=0)
            or not math.isfinite(center_rho) or center_rho<=0):
        raise ValueError("Invalid RNS thermodynamic table or center")
    rho,p=rows[:,0],rows[:,1]
    if not rho[0]<=center_rho<=rho[-1]:
        raise ValueError("center outside exact RNS table support")
    i=min(max(0,int(np.searchsorted(rho,center_rho,side="right")-1)),len(rho)-2)
    a,b=float(rho[i]),float(rho[i+1])
    p0,p1=float(p[i]),float(p[i+1])
    cs2_secant=(p1-p0)/((b-a)*C_CGS**2)
    gamma=(math.log(p1)-math.log(p0))/(math.log(b)-math.log(a))
    p_center=math.exp(math.log(p0)+gamma*(math.log(center_rho)-math.log(a)))
    cs2_local_powerlaw=gamma*p_center/(center_rho*C_CGS**2)
    return {"rho_bracket_g_cm3":[a,b],
            "p_bracket_dyn_cm2":[p0,p1],
            "bracket_index":i,
            "center_rho_g_cm3":float(center_rho),
            "local_logP_logRho_gamma":gamma,
            "table_secant_dp_de":cs2_secant,
            "table_local_powerlaw_dp_de":cs2_local_powerlaw,
            "rns_table_density_monotone":True,
            "rns_table_pressure_monotone":True,
            "warning":"These two finite-resolution slopes are sensitivity proxies, not an exact C/RNS interpolation derivative."}


def audit(rns,source_dir:Path,workdir:Path):
    if (rns.get("status")!="ALL_SEVEN_VALIDATED"
            or rns.get("validated_eos_count")!=7
            or set(rns.get("eos",{}))!=set(EOS)
            or rns.get("jester_upstream_commit")!=SOURCE_COMMIT):
        raise ValueError("Pinned successful RNS 7-EOS identity check failed")
    out={}
    for name in EOS:
        model=rns["eos"][name]
        if model.get("status")!="MATCHED_FIXED_MASS_RNS_GR_AND_STATIC_TOV_VALIDATED":
            raise ValueError(f"{name}: source RNS model not validated")
        src=source_dir/(name+".npz")
        srcsha=hashlib.sha256(src.read_bytes()).hexdigest()
        if model["source_npz_sha256"]!=srcsha:raise ValueError(f"{name}: source NPZ mismatch")
        rows,info=from_jester_npz(src,points=196)
        if info["source_npz_sha256"]!=srcsha:raise ValueError("Source SHA check failed")
        dst=workdir/(name+".rns")
        write_rns(dst,rows)
        table_sha=hashlib.sha256(dst.read_bytes()).hexdigest()
        if table_sha!=model["rns_table_sha256"]:
            raise ValueError(f"{name}: regenerated 196pt EOS table SHA mismatch")
        rho=float(model["rns_rotating_at_target"]["central_energy_density_g_cm3"])
        vals=eos_table_slopes(rows,rho)
        vals.update({"eos":name,"source_npz_sha256":srcsha,
                     "regenerated_exact_RNS_196pt_table_sha256":table_sha,
                     "rns_center_mass_msun":float(model["rns_rotating_at_target"]["mass_msun"]),
                     "rns_center_spin_hz_reported":float(model["rns_rotating_at_target"]["spin_hz_reported"]),
                     "source_table_points":info["source_points"],
                     "rns_table_points":info["output_points"]})
        out[name]=vals
    return {"schema":"j0740-seven-RNS-exact-table-cs2-sensitivity-v1",
            "status":"EXACT_SEVEN_RNS_TABLE_SHA_MATCH_REPRODUCED",
            "source_commit":SOURCE_COMMIT,"pinned_rns_workflow_run":42353019033,
            "pinned_rns_json_sha256":RNS_JSON_SHA256,
            "interpretation":"RNS 196-pt EOS table resampling slope vs original native source, never full EOS posterior",
            "eos":out}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rns-json",type=Path,required=True)
    p.add_argument("--jester-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    raw=a.rns_json.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=RNS_JSON_SHA256:
        raise ValueError("Pinned RNS artifact JSON SHA mismatch")
    a.out.parent.mkdir(parents=True,exist_ok=True)
    evidence=audit(json.loads(raw),a.jester_dir,a.out.parent)
    a.out.write_text(json.dumps(evidence,indent=2,sort_keys=True)+"\n")
    for n,r in evidence["eos"].items():
        print(n,"same_table_sha",r["regenerated_exact_RNS_196pt_table_sha256"],
              "secant",r["table_secant_dp_de"],
              "powerlaw",r["table_local_powerlaw_dp_de"],flush=True)


if __name__=="__main__":main()
