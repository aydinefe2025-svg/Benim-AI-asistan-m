"""Audit pinned seven JESTER source EOS tables across their sampled stellar ranges.

CLI: python run_source_native_global_gate.py --fixture pinned_eos_center_fixture.json \
  --fetch-pinned --out-dir ./outputs

This is *source-wide* sampled evidence, not proof between knots or a new EOS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

import numpy as np
from source_native_global_gate import audit_arrays

C=299792458.0
G=6.67430e-11
CGS_RHO_PER_GEOM_E=C*C/G*1e-3
UPSTREAM='https://raw.githubusercontent.com/nuclear-multimessenger-astronomy/jester'
EOS=('APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2')


def sha256_file(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):
   h.update(chunk)
 return h.hexdigest()


def audit_one(name, info, path):
    digest=sha256_file(path)
    if digest!=info['expected_source_sha256']:
        raise ValueError(f'{name} SOURCE SHA MISMATCH: {digest}')
    with np.load(path,allow_pickle=False) as npz:
        required={'e','p','h','n','cs2','dloge_dlogp'}
        if not required.issubset(set(npz.files)):
            raise ValueError(f'{name} missing source thermodynamic arrays')
        p,e,n,h,cs2=(np.asarray(npz[k],dtype=np.float64) for k in ('p','e','n','h','cs2'))
        dlog=np.asarray(npz['dloge_dlogp'],dtype=np.float64)
    if len(e)!=info['expected_source_rows']:
        raise ValueError(f'{name} SOURCE ROW COUNT MISMATCH')
    eps=(info['center_rho_g_cm3']/CGS_RHO_PER_GEOM_E)
    result=audit_arrays(p,e,n,h,cs2,center_e=eps)
    analytic_consistency=np.max(np.abs(cs2 - p/(e*dlog)))
    if not np.isfinite(analytic_consistency) or analytic_consistency>1e-8:
        raise ValueError(f'{name} SOURCE ANALYTIC CS2 IDENTITY MISMATCH: {analytic_consistency}')
    if result['source_energy_nonincreasing_edges_global']!=info['expected_source_energy_nonincreasing_edges_global']:
        raise ValueError(f'{name} native source-monotonicity identity disagrees with source forensics')
    if result['native_cs2_nonpositive_nodes_global']!=info['expected_native_negative_count_global']:
        raise ValueError(f'{name} native cs2 negative count differs from pinned prior audit')
    result.update({'source_name':name,'source_npz_sha256':digest,'source_npz_bytes':path.stat().st_size,
                   'source_native_analytic_cs2_identity_max_error':float(analytic_consistency),
                   'center_rho_g_cm3':info['center_rho_g_cm3']})
    return result


def generate_report(fixture, source_dir, out_dir, fetch=False):
    if fixture['source_commit']!='e6768650ce992abfd1153a6833857572fe5cd230':
        raise ValueError('Upstream source pin changed')
    if set(fixture['eos'])!=set(EOS):
        raise ValueError('Expected exact 7 EOS identities')
    source_dir.mkdir(parents=True,exist_ok=True)
    out_dir.mkdir(parents=True,exist_ok=True)
    result={
        'schema':'j0740-pinned-native-seven-eos-whole-tabulation-screen-v1',
        'source_commit':fixture['source_commit'],
        'previous_7GR_json_sha256':fixture['RNS_GR_original_json_sha256'],
        'original_source_center_audit_sha256':fixture['source_center_audit_sha256'],
        'scope':'Native sampled-node and source log-linear interpolation screen; not a certified continuous EOS; no physical model correction; no new GR solver or Bayesian EOS evidence',
        'eos':{}
    }
    for name in EOS:
        path=source_dir/(name+'.npz')
        if not path.exists() and fetch:
            url=f'{UPSTREAM}/{fixture["source_commit"]}/jesterTOV/tabulated_eos/lalsuite/{name}.npz'
            # Download only tiny exact-source (~50kB) NPZs, never NICER 12.9GB archive.
            with urllib.request.urlopen(url,timeout=35) as stream:
                blob=stream.read(1000000)
            if hashlib.sha256(blob).hexdigest()!=fixture['eos'][name]['expected_source_sha256']:
                raise ValueError(name+' fetched upstream source SHA invalid; refusing to write')
            path.write_bytes(blob)
        if not path.is_file():
            raise FileNotFoundError(f'{name} missing pinned original NPZ')
        result['eos'][name]=audit_one(name,fixture['eos'][name],path)
        print(name,result['eos'][name]['sampled_source_screen'],flush=True)
    result['sampled_source_pass_names']=[name for name in EOS if result['eos'][name]['sampled_source_screen']=='SAMPLED_PASS_NOT_GLOBAL_PROOF']
    result['sampled_source_fail_names']=[name for name in EOS if name not in result['sampled_source_pass_names']]
    if result['sampled_source_pass_names']!=['APR4_EPP']:
        raise AssertionError('Source-wide sampled in-star classification unexpected')
    p=out_dir/'J0740_FULL_SOURCE_NATIVE_7EOS_GATE_20261116.json'
    p.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf8')
    lines=['# J0740 — seven complete pinned JESTER native-EOS table screens',
           '','**Original whole tabulations tested; NO simulated physical repair.**',
           '','Pinned upstream commit: `'+fixture['source_commit']+'`',
           '','| EOS | Source nodes | Native negative cs2 below rotating center | Native superluminal cs2 below center | Source e reversal edges | Sampled in-star gate | First-law n terminal mismatch |',
           '|---|---:|---:|---:|---:|---|---:|']
    for name,record in result['eos'].items():
        lines.append(f"| {name} | {record['N_source_nodes']} | {record['negative_native_cs2_below_center']} | {record['superluminal_native_cs2_below_center']} | {record['source_energy_nonincreasing_edges_global']} | {record['sampled_source_screen']} | {100*record['firstlaw_n_normalized_terminal_fractional_mismatch']:.3f}% |")
    lines += ['','## Interpretation',
      '- APR4_EPP is the only one of these seven source samples without *sampled* intrinsic sound-speed or energy monotonicity failures at densities up to this historical rotating-star center. No certification between nodes.',
      '- ENG, WFF1, WFF2 contain native superluminal values within the rotating star; all six non-APR4 cases share one original low-pressure native negative-cs2/reversed-energy interval.',
      '- “First-law n mismatch” is the global difference between original n=e/m_avg approximation and integrated cold EOS dln(n)=dE/(E+P), **conditional on piecewise log-linear E(P)**; not a direct claim that an LALSuite solver is broken.',
      '- A source analytic sound speed sampled at nodes is NOT proof of global physical causality between all nodes or past the rotating stellar center.',
      '- APR4_EPP has a global source-table cs2>1 region *above* this historical model center. This remains a limitation for the EOS at higher central density.',
      '- No physical crust construction, zero-pressure surface extension, GR rotating re-solve, X-PSI nuisance correction or Bayesian EOS evidence is performed.',
      '','JSON with original SHA256 of all seven NPZ inputs: `'+p.name+'`',
      'Reproducible source: `source_native_global_gate.py`, `run_source_native_global_gate.py`, `test_source_native_global_gate.py`.',
      '']
    md=out_dir/'J0740_FULL_SOURCE_NATIVE_7EOS_GATE_20261116.md'
    md.write_text('\n'.join(lines),encoding='utf8')
    return result,p,md


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--fixture',type=Path,default=Path(__file__).with_name('pinned_eos_center_fixture.json'))
    ap.add_argument('--source-dir',type=Path,default=Path(__file__).with_name('pinned_source_npz'))
    ap.add_argument('--out-dir',type=Path,default=Path(__file__).with_name('outputs'))
    ap.add_argument('--fetch-pinned',action='store_true')
    args=ap.parse_args()
    fixture=json.loads(args.fixture.read_text(encoding='utf8'))
    result,j,m=generate_report(fixture,args.source_dir,args.out_dir,fetch=args.fetch_pinned)
    print(json.dumps({'status':'SAMPLED_SOURCE_SCREEN_COMPLETED','sampled_pass':result['sampled_source_pass_names'],'sampled_fail':result['sampled_source_fail_names'],'json':str(j),'markdown':str(m)},sort_keys=True))


if __name__=='__main__':
    main()
