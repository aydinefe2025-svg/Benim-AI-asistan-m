"""Run APR4 full source PCHIP centre-truncated screen and MPA1 fail-closed control."""
from pathlib import Path
import argparse, json, hashlib
from apr4_center_continuous import audit_pinned_npz, SourceInvalid

JESTER_PIN='e6768650ce992abfd1153a6833857572fe5cd230'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source-dir',type=Path,required=True)
    ap.add_argument('--fixture',type=Path,required=True)
    ap.add_argument('--out-dir',type=Path,default=Path('.'))
    opt=ap.parse_args()
    source=json.loads(opt.fixture.read_text())
    assert source['source_commit']==JESTER_PIN
    result={'schema':'J0740_APR4_center_continuous_candidate_v1','source_commit':JESTER_PIN,
            'fixture_sha256':sha(opt.fixture),
            'screen_scope':'APR4 continuous log(e) vs log(P) PCHIP candidate to J0740 RNS centre; MPA1 source nonmonotonic negative control',
            'model':{},'physics_accepted':False,
            'explicit_nonclaims':['No LALSuite native function between-knot certification','No P=0 crust','No first-law n(P) normalization or enthalpy closure','No new RNS or TOV solver','No seven-model discrete Bayes posterior']}
    for name in ['APR4_EPP','MPA1']:
        p=opt.source_dir/(name+'.npz')
        try:
            v=audit_pinned_npz(p,source['eos'][name])
            if name=='MPA1':raise AssertionError('Known MPA1 negative source secant was not rejected!')
            result['model'][name]=v
        except SourceInvalid as e:
            if name!='MPA1':raise
            result['model'][name]={'interpolant_status':'SOURCE_REJECTED_NONMONOTONIC_NO_INTERPOLATION','reason':str(e),
                                  'source_sha256':sha(p)}
    result['status']='PASS_SOURCE_PIN_AND_FAIL_CLOSED_DIAGNOSTICS'
    opt.out_dir.mkdir(parents=True,exist_ok=True)
    q=opt.out_dir/'J0740_APR4_CENTER_CONTINUOUS_PCHIP_GATE_20261117.json'
    q.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+'\n')
    a=result['model']['APR4_EPP'];b=result['model']['MPA1']
    lines=['# J0740 EOS source-native data: APR4 continuous between-knot PCHIP screen',
     '',
     'This is **not** native LALSuite continuous physical EOS certification, not a new star model, nor seven-model Bayes evidence.',
     '',
     '| test | result |','|---|---|',
     f'| APR4 original pinned source SHA256 | `{a["source_sha256"]}` |',
     f'| APR4 J0740 RNS centre pressure (geometric m^-2) | {a["p_center"]:.12e} |',
     f'| APR4 centre-truncated PCHIP exact-interval max c_s²/c² | {a["pchip_center_truncated_cs2_max"]:.12f} |',
     f'| APR4 centre-truncated native sampled max c_s²/c² | {a["source_native_center_truncated_cs2_max"]:.12f} |',
     f'| APR4 PCHIP candidate status | {a["interpolant_status"]} |',
     f'| APR4 first native superluminal source e/centre | {a["native_first_superluminal_node_energy_over_center"]:.9f} |',
     f'| MPA1 source negative control | {b["interpolant_status"]} |',
     '',
     'Exact extrema of c_s² under the log(P)-log(e) PCHIP interpolant were located by cubic-derivative and quartic stationarity equations in each P interval **up to centre**; independently checked by 61 dense points per interval.',
     'This candidate is mathematical only: continuous native LALSimulation EOS can be different, pressure-to-zero crust is missing, n(P), h(P) normalization and RNS physical validation remain open.',
     'No source NPZ was modified. The negative-control EOS was explicitly rejected rather than auto-smoothed.',
     '',
     'JSON: `J0740_APR4_CENTER_CONTINUOUS_PCHIP_GATE_20261117.json`. Reproduce with this runner and source SHA-pinned small JESTER NPZ.']
    m=opt.out_dir/'J0740_APR4_CENTER_CONTINUOUS_PCHIP_GATE_20261117.md'
    m.write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps({'status':result['status'],'apr4_candidate':a['interpolant_status'],'apr4_pchip_max':a['pchip_center_truncated_cs2_max'],'mpa1_negative':b['interpolant_status'],'json':str(q),'md':str(m)}))

if __name__=='__main__':main()
