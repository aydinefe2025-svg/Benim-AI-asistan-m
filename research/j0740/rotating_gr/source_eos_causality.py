"""Source-native JESTER sound-speed/casuality screen for seven EOS.

The exact pinned JESTER NPZ contains an analytic cs2 array (cs^2/c^2).
This is preferable to raw finite differences of the source e,p array, whose
low-energy e entries need not be monotonically increasing. Keep source order
and report those anomalies rather than hiding them with a sort or EOS fit.
This is a thermodynamic-model screen, NOT NICER photon inference.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

G,C = 6.67430e-11, 299792458.0
EOS_NAMES=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")
JESTER_COMMIT="e6768650ce992abfd1153a6833857572fe5cd230"

def profile(e,p,cs2):
    e=np.asarray(e,float)
    p=np.asarray(p,float)
    cs2=np.asarray(cs2,float)
    if (e.ndim!=1 or e.size<100 or e.shape!=p.shape or e.shape!=cs2.shape
            or not np.all(np.isfinite(e+p+cs2))
            or np.any(e<=0) or np.any(p<=0) or np.any(cs2<0)
            or np.any(np.diff(p)<=0)):
        raise ValueError("Native source e,p,cs2 arrays invalid, refuse to infer causality")
    bad=np.where(cs2>1.+1e-8)[0]
    i=int(bad[0]) if len(bad) else None
    return {
        "native_cs2_max":float(np.max(cs2)),
        "source_cs2_max":float(np.max(cs2)),
        "source_nodes":int(len(e)),
        "raw_energy_nonincreasing_segments":int(np.count_nonzero(np.diff(e)<=0)),
        "native_superluminal_node_count":int(len(bad)),
        "first_superluminal_index":i,
        "first_superluminal_central_density_g_cm3":float(e[i]*C*C/G*1e-3) if i is not None else None,
        "status":"SOURCE_NATIVE_CS2_SCREEN_PASS" if i is None else "SOURCE_NATIVE_CS2_SUPERLUMINAL",
        "method":"Pinned JESTER source cs2 array, native geometric energy density e[m^-2] converted to equivalent mass density g/cm^3",
        "caveat":"Compare source sound speed threshold with each actual rotating-model central density; static mass threshold cannot simply be reused. Not full likelihood or EOS posterior."
    }

def diagnose(file):
    with np.load(file,allow_pickle=False) as src:
        required={"e","p","cs2"}
        if not required.issubset(src.files):
            raise ValueError(f"{file.name}: no complete native e,p,cs2, found {sorted(src.files)}")
        result=profile(src["e"],src["p"],src["cs2"])
    result["eos"]=file.stem
    result["source_npz_sha256"]=hashlib.sha256(file.read_bytes()).hexdigest()
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--jester-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    rows={name:diagnose(a.jester_dir/(name+".npz")) for name in EOS_NAMES}
    output={"schema":"source-native-jester-eos-cs2-v1","jester_commit":JESTER_COMMIT,
            "interpretation":"screen of exact source-native cs2, not GR or Bayesian inference","eos":rows}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
    for name,r in rows.items():
        print(name,r["status"],"cs2_max",r["source_cs2_max"],
              "first_superluminal_rho",r["first_superluminal_central_density_g_cm3"],flush=True)

if __name__=="__main__":main()
