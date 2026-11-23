#!/usr/bin/env python3
"""Source-pinned APR4 spin anchor by direct RNS -r, bypassing upstream SetSpin.

Numerical consistency test only; a local rotating star does not establish EOS
microphysics, global stability, or NICER/XMM photon likelihood.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from scipy.optimize import brentq

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'f63'))
sys.path.insert(0,str(HERE.parent/'f135'))
from f63_original_mpa1_fixed_J import c_call,fixed_j_at_density
from f135_original_apr4_local_fixed_j import source_gate,from_jester_npz,write_rns,ANCHOR_E,SPIN_HZ

def run(source,binary,out):
    source_gate(source)
    tab,_=from_jester_npz(source,points=196)
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    table=out.parent/'APR4_EPP_F137_original_196.rns';write_rns(table,tab)
    trace=[];cache={}
    def probe(r):
        r=round(float(r),10)
        if r not in cache:
            v=c_call(binary,table,ANCHOR_E,ratio=r)
            cache[r]=v
            trace.append({'r':r,'f_hz':v['spin_hz'],'J_cgs':v['J_cgs']})
        return cache[r]
    a,b=probe(.98),probe(.99)
    if (a['spin_hz']-SPIN_HZ)*(b['spin_hz']-SPIN_HZ)>=0:raise ValueError('F137_FREQUENCY_NOT_BRACKETED')
    rr=brentq(lambda x:probe(x)['spin_hz']-SPIN_HZ,.98,.99,xtol=2e-10,rtol=2e-10)
    anchor=probe(rr)
    samej=fixed_j_at_density(lambda e,r:c_call(binary,table,e,ratio=r),ANCHOR_E,anchor['J_cgs'],rr)
    result={'schema':'J0740_F137_DIRECT_RATIO_SPIN_ROOT_V1',
            'source_sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),
            'table_sha256':hashlib.sha256(table.read_bytes()).hexdigest(),
            'binary_sha256':hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
            'target_spin_hz':SPIN_HZ,'anchor':anchor,'same_J_replay':samej,
            'frequency_residual_hz':anchor['spin_hz']-SPIN_HZ,
            'mass_replay_difference_msun':samej['mass_msun']-anchor['mass_msun'],
            'J_replay_relative_residual':samej['relative_J_residual'],
            'direct_ratio_trace':trace,
            'scope':'NUMERICALLY_CONSISTENT_LOCAL_STAR_NOT_GLOBAL_PHYSICAL_EOS_POSTERIOR'}
    if not (abs(result['frequency_residual_hz'])<.002 and
            abs(result['mass_replay_difference_msun'])<1e-5 and
            abs(result['J_replay_relative_residual'])<1e-7):
        raise ValueError('F137_DIRECT_MODEL_REPLAY_FAILED')
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print('F137',result['frequency_residual_hz'],result['mass_replay_difference_msun'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--rns',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.source,a.rns,a.out)
