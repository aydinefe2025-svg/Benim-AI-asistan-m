from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
C_CM_S = 29979245800.0
MAVG_G = 1.673774710865e-24
RNS_MB_G = 1.66e-24
EXPECTED = {
    'native_approx': 'c8f4da82524a5e0b3450c682198359078deb78d573a1f50f2487235df16d88c7',
    'firstlaw_mavg': 'b5f2c4fd88aecece0ab589a6266b022394d6d7da4ea87942fb493aa064f4f1f2',
    'firstlaw_rns_mb': 'c96df32fc0907df107b8d805c009b2a39efb4836807a07373e719967fda59a16',
}
def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
def read_table(path: Path):
    raw=path.read_bytes(); lines=raw.decode('ascii').splitlines()
    count=int(lines[0].strip()); data=np.loadtxt(path,skiprows=1)
    if count != 196 or data.shape != (196,4) or not np.isfinite(data).all():
        raise AssertionError(f'invalid table shape/content: {path.name}')
    if np.any(data <= 0) or not np.all(np.diff(data,axis=0)>0):
        raise AssertionError(f'nonpositive/nonmonotone table: {path.name}')
    return data, sha(raw), len(raw)
def inspect_mesh(root: Path, label: str):
    work=root/'work'
    tables={k:read_table(work/f'apr4_{k}.rns') for k in EXPECTED}
    for k,(_,digest,_) in tables.items():
        if digest != EXPECTED[k]: raise AssertionError(f'{label}: EOS table hash mismatch: {k}')
    ref=tables['native_approx'][0]
    for k,(arr,_,_) in tables.items():
        if not np.array_equal(arr[:,:3],ref[:,:3]):
            raise AssertionError(f'{label}: first three EOS columns changed for {k}')
    if any(np.array_equal(tables['native_approx'][0][:,3],tables[k][0][:,3]) for k in ('firstlaw_mavg','firstlaw_rns_mb')):
        raise AssertionError(f'{label}: n-only ablation did not modify n')
    # RNS H is offset to 1 at the positive-pressure first row. For the first-law
    # differential identity, only its varying part is relevant; the ratio must
    # be constant over the truncated table if n(P) has the right shape.
    pbar=ref[:,1]/(C_CM_S*C_CM_S)
    ebar=ref[:,0]
    hrel=(ref[:,2]-ref[0,2])/(C_CM_S*C_CM_S)
    shape={}
    for k in EXPECTED:
        n=tables[k][0][:,3]
        invariant=n*np.exp(hrel)/(ebar+pbar)
        rel=(invariant/invariant[0])-1.0
        shape[k]={'max_abs_relative_drift':float(np.max(np.abs(rel))),
                  'rms_relative_drift':float(np.sqrt(np.mean(rel**2))),
                  'endpoint_relative_drift':float(rel[-1]),
                  'constant_within_1e-10':bool(np.max(np.abs(rel)) < 1e-10)}
    if not shape['firstlaw_mavg']['constant_within_1e-10'] or not shape['firstlaw_rns_mb']['constant_within_1e-10']:
        raise AssertionError(f'{label}: h-based n table fails first-law shape identity')
    return {'mesh':label,'rows':196,'table_sha256':{k:tables[k][1] for k in EXPECTED},
            'table_bytes':{k:tables[k][2] for k in EXPECTED},
            'first_three_columns_bitwise_equal':True,'n_column_changed_only':True,
            'firstlaw_shape_identity':shape}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('artifact_dir',type=Path); ap.add_argument('artifact_zip',type=Path); ap.add_argument('output',type=Path); a=ap.parse_args()
    source=a.artifact_dir/'J0740_APR4_PRECISE_ROOT_N_ONLY_ABLATION_20261117.json'
    raw=source.read_bytes(); doc=json.loads(raw)
    if doc['status']!='PASS_CONDITIONAL_N_ONLY_ABLATION_GEOMETRY_INVARIANT': raise AssertionError('workflow status mismatch')
    meshes=[]
    for m in doc['meshes']:
        entry=inspect_mesh(a.artifact_dir,m['grid'])
        runs=m['runs']; base=runs['native_approx']
        for variant in ('firstlaw_mavg','firstlaw_rns_mb'):
            for f in ('mass_msun','spin_hz','radius_eq_km'):
                if runs[variant][f] != base[f]: raise AssertionError(f'{m["grid"]}: geometry changed under n-only transform')
        r1=runs['firstlaw_rns_mb']['rns_M0_using_native_Mb_msun']/runs['firstlaw_mavg']['rns_M0_using_native_Mb_msun']
        expected=MAVG_G/RNS_MB_G
        if abs(r1/expected-1)>3e-7: raise AssertionError(f'{m["grid"]}: MB convention factor mismatch')
        entry['geometry_outputs_bitwise_equal']=True
        entry['measured_RNS_MB_over_mavg_mass_ratio']=r1
        entry['expected_mavg_over_RNS_MB']=expected
        entry['factor_relative_error']=float(r1/expected-1)
        entry['conditional_M0_msun']={k:runs[k]['rns_M0_using_native_Mb_msun'] for k in runs}
        meshes.append(entry)
    out={'schema':'j0740-apr4-n-only-ablation-independent-firstlaw-table-check-v1',
         'classification':'INDEPENDENT_ARTIFACT_TABLE_ARITHMETIC_CHECK_ONLY; PHYSICAL_SURFACE_NORMALIZATION_NOT_ESTABLISHED',
         'inputs':{'workflow_run_id':44050619643,'commit':'9bb301323ee1c1dc25b3dbc239ed7b9797bec21c',
                   'workflow_artifact_sha256':sha(a.artifact_zip.read_bytes()),
                   'workflow_result_json_sha256':sha(raw),'source_npz_sha256':doc['source']['jester_npz_sha256'],
                   'source_rns_table_sha256':doc['source']['root_table_sha256']},
         'method':'Independently parse saved 196-row RNS tables; check SHA, bitwise invariance of epsilon/P/H, first-law shape invariant n*exp(h_relative)/(epsilon+P/c^2), identical M_g/R_eq/f and RNS-MB conversion ratio.',
         'meshes':meshes,
         'acceptance':{'table_hashes_pass':True,'geometry_invariance_pass':True,'firstlaw_n_shape_pass':True,
                       'absolute_baryon_normalization':'NOT_ESTABLISHED','P_to_zero_crust':'NOT_ESTABLISHED',
                       'physical_EOS_certification':'NOT_ESTABLISHED','EOS_Bayes':'NOT_RUN'}}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'output':str(a.output),'bytes':a.output.stat().st_size,'sha256':sha(a.output.read_bytes()),'result':out},indent=2))
if __name__=='__main__': main()

