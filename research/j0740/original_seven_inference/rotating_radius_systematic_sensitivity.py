"""Numerical sensitivity only: common and independent radius offsets, not RNS rotating seven stars."""
from __future__ import annotations
import argparse,zipfile,io,json
from pathlib import Path
import numpy as np
from original_seven_fullmass_integral import load_eos,load_surface,model_integration,PINNED_NPZ_SHA

def radius_shift_integral(ez,fz,offsets):
    eos={name:load_eos(ez,name) for name in sorted(PINNED_NPZ_SHA)}
    fits={key:load_surface(fz,key)[0] for key in ('weighted_0.015_0.20','weighted_0.025_0.35','weighted_0.040_0.50','resampled_0.015_0.20','resampled_0.025_0.35','resampled_0.040_0.50')}
    output={}
    for delta in offsets:
        runs=[]
        for key,fit in fits.items():
            vals={name:model_integration(lambda m,c=curve,d=delta:c(m)+d,mmax,fit)['value'] for name,(curve,mmax,_,_) in eos.items()}
            den=sum(vals.values())
            runs.append({name:val/den for name,val in vals.items()})
        output[str(delta)]={name:{'median_fraction':float(np.median([r[name] for r in runs])), 'range_fraction':[float(min(r[name] for r in runs)),float(max(r[name] for r in runs))]} for name in eos}
    return output

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--eos',type=Path,required=True);ap.add_argument('--f38',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    with zipfile.ZipFile(args.eos) as ez,zipfile.ZipFile(args.f38) as fz:
       v=radius_shift_integral(ez,fz,[-.30,-.082,0,.082,.30])
    args.out.write_text(json.dumps({'kind':'uniform_radius_shift_sensitivity_ONLY_not_actual_rotating_stars','conditional_seven_source_static_plus_radius_shifts':v},indent=2,sort_keys=True)+'\n')
    for d in v:
       print('SHIFT_KM',d,'MPA1',round(v[d]['MPA1']['median_fraction'],4),'ENG',round(v[d]['ENG']['median_fraction'],4),'winner',max(v[d],key=lambda k:v[d][k]['median_fraction']))
