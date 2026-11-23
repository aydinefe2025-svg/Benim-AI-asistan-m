#!/usr/bin/env python3
"""Test whether original RNS SetSpin float root causes the APR4 -s/-r mismatch.

Only the numeric root search declaration is changed; Einstein/model equations
and the original source EOS remain pinned. Results are a diagnostic, not a
physical EOS stability certificate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'f63'))
sys.path.insert(0,str(HERE.parent/'f135'))
from f63_original_mpa1_fixed_J import c_call, fixed_j_at_density
from f135_original_apr4_local_fixed_j import source_gate, from_jester_npz, write_rns, ANCHOR_E, SPIN_HZ

OLD='float ans, fh,fl,fm,fnew,sroot,xh,xl,xm,xnew,xacc=1e-5;'
NEW='double ans, fh,fl,fm,fnew,sroot,xh,xl,xm,xnew,xacc=1e-10;'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def patch_spin_source(text):
    if text.count(OLD)!=1 or NEW in text:
        raise ValueError('F136_PINNED_SPIN_ROOT_SIGNATURE_DRIFT')
    out=text.replace(OLD,NEW)
    if out.count(NEW)!=1:raise ValueError('F136_PATCH_NOT_UNIQUE')
    return out


def measure(source,binary,out):
    source_gate(source)
    table,_=from_jester_npz(source,points=196)
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    table_path=out.parent/'APR4_EPP_F136_original_196.rns'
    write_rns(table_path,table)
    spin=c_call(binary,table_path,ANCHOR_E,frequency=SPIN_HZ)
    fixed=fixed_j_at_density(lambda ee,r:c_call(binary,table_path,ee,ratio=r),ANCHOR_E,spin['J_cgs'],.985)
    result={'schema':'J0740_F136_SETSPIN_PRECISION_SAME_J_V1',
            'source_npz_sha256':sha(source),'table_sha256':sha(table_path),'binary_sha256':sha(binary),
            'requested_spin_hz':SPIN_HZ,'spin_mode':spin,'fixed_J_mode':fixed,
            'same_input_central_density_g_cm3':ANCHOR_E,
            'spin_mode_frequency_residual_hz':spin['spin_hz']-SPIN_HZ,
            'spin_minus_fixed_J_mass_msun':spin['mass_msun']-fixed['mass_msun'],
            'spin_minus_fixed_J_frequency_hz':spin['spin_hz']-fixed['spin_hz'],
            'fixed_J_relative_residual':fixed['relative_J_residual'],
            'scope':'ISOLATED_C_NUMERICAL_ROOT_PRECISION_TEST_NOT_GLOBAL_PHYSICAL_EOS_ACCEPTANCE'}
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print('F136_SAME_J',json.dumps({k:result[k] for k in ('spin_mode_frequency_residual_hz','spin_minus_fixed_J_mass_msun','spin_minus_fixed_J_frequency_hz','fixed_J_relative_residual')}),flush=True)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('patch','measure'),required=True)
    p.add_argument('--findmodel',type=Path);p.add_argument('--source',type=Path)
    p.add_argument('--rns',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.mode=='patch':
        s=a.findmodel.read_text();a.findmodel.write_text(patch_spin_source(s))
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps({'old_findmodel_sha256':hashlib.sha256(s.encode()).hexdigest(),'patched_findmodel_sha256':sha(a.findmodel),'patch_scope':'SetSpin float Ridder variables to double and xacc 1e-5 to 1e-10 only'},indent=2)+'\n')
    else:measure(a.source,a.rns,a.out)


if __name__=='__main__':main()
