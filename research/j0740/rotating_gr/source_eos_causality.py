"""Finite-difference causality screen on pinned native JESTER EOS e,p tables.

e and p are in geometric SI (m^-2), hence c_s^2/c^2 = dp/de.
This is a *table derivative diagnostic*, not a formal EOS validity proof.
"""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
import numpy as np

G,C=6.67430e-11,299792458.
NAMES=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")

def diagnose(path):
    with np.load(path,allow_pickle=False) as data:
        e=np.asarray(data["e"],float)
        p=np.asarray(data["p"],float)
    if (e.ndim!=1 or e.size<100 or p.shape!=e.shape
            or not np.all(np.isfinite(e+p))
            or np.any(e<=0) or np.any(p<=0)
            or np.any(np.diff(e)<=0) or np.any(np.diff(p)<=0)):
        raise ValueError("JESTER source e,p tables invalid/nonmonotone")
    vsq=np.diff(p)/np.diff(e)
    idx=np.where(vsq>1.0+1e-8)[0]
    rho=e*C*C/G*1e-3
    i=int(idx[0]) if len(idx) else None
    return {
      "eos":path.stem,"source_nodes":len(e),
      "geometric_units":"e,p both m^-2; dp/de = sound speed squared / c²",
      "source_rho_min_g_cm3":float(rho[0]),"source_rho_max_g_cm3":float(rho[-1]),
      "finite_difference_vsound2_over_c2_max":float(vsq.max()),
      "n_superluminal_intervals":int(len(idx)),
      "first_superluminal_interval_index":i,
      "first_superluminal_interval_rho_low_g_cm3":float(rho[i]) if i is not None else None,
      "first_superluminal_interval_rho_high_g_cm3":float(rho[i+1]) if i is not None else None,
      "global_causality_status":"SCREEN_PASS" if i is None else "SOURCE_TABLE_SUPERLUMINAL_SEGMENTS_PRESENT",
      "warning":"Do not infer a full rotating-star physical exclusion solely from this source finite-difference screen",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--jester-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    d={name:diagnose(a.jester_dir/(name+".npz")) for name in NAMES}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(d,indent=2,sort_keys=True)+"\n")
    for name,entry in d.items():
        print(name,entry["global_causality_status"],
              "onset_rho",entry["first_superluminal_interval_rho_low_g_cm3"],
              "max_csound2",entry["finite_difference_vsound2_over_c2_max"],flush=True)

if __name__=="__main__":main()
