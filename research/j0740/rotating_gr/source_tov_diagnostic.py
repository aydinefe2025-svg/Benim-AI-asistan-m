"""Inspect pinned JESTER M-R source order without interpolating over unstable parts."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np

EOS=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")
TARGET_M=2.073

def diagnose(file:Path)->dict:
    with np.load(file,allow_pickle=False) as z:
        mass=np.asarray(z["masses_EOS"],dtype=float)
        radius=np.asarray(z["radii_EOS"],dtype=float)
    if mass.ndim!=1 or radius.shape!=mass.shape or len(mass)<10 or not np.all(np.isfinite(mass+radius)):
        raise ValueError("Invalid source M/R")
    peak=int(np.argmax(mass))
    declines=np.where(np.diff(mass[:peak+1])<=0)[0]
    crossing=np.where((mass[:-1] < TARGET_M)&(mass[1:] >= TARGET_M))[0]
    i=int(crossing[0]) if len(crossing) else None
    local_ok=(i is not None and i<peak and np.all(np.diff(mass[max(0,i-5):min(peak+1,i+7)])>0))
    return {
      "eos":file.stem,"nodes":len(mass),"mass_min":float(mass.min()),
      "mass_max":float(mass.max()),"global_mass_peak_index":peak,
      "decline_count_before_global_peak":int(len(declines)),
      "decline_pairs":[{"i":int(j),"m_before":float(mass[j]),
                         "m_after":float(mass[j+1]),
                         "dm":float(mass[j+1]-mass[j])} for j in declines[:15]],
      "first_target_crossing_index":i,
      "local_mass_monotone_at_target":bool(local_ok),
      "first_crossing_MR":[{"M":float(mass[k]),"R":float(radius[k])}
          for k in ([i,i+1] if i is not None else [])],
      "mass_near_global_peak":[float(v) for v in mass[max(0,peak-8):peak+1]],
      "post_global_peak_nodes":len(mass)-peak-1
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--jester-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    records={k:diagnose(a.jester_dir/(k+".npz")) for k in EOS}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(records,indent=2,sort_keys=True)+"\n")
    for k,x in records.items():print(k, "mass_max", x["mass_max"],"declines",x["decline_pairs"],"local_target_ok",x["local_mass_monotone_at_target"],flush=True)

if __name__=="__main__":main()
