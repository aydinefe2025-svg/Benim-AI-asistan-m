#!/usr/bin/env python3
"""F75: source-byte-pinned, *sampled* EOS c_s^2 gates at actual RNS C central densities.

Input JESTER LALSimulation .npz and the *original* GitHub Actions RNS C
artifact ZIPs (base64). Does NOT construct a new EOS, fit photons, certify
continuum causality, make a full EOS Bayesian inference, or rerun RNS.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile
import numpy as np

EOS = ('APR4_EPP', 'ENG', 'MPA1', 'MS1', 'MS1B', 'WFF1', 'WFF2')
G_SI = 6.67430e-11
C_SI = 299792458.0
GEOM_E_TO_G_CM3 = C_SI**2 / G_SI / 1000.0
REF_MASS = 2.073


def digest(b):
    return hashlib.sha256(b).hexdigest()


def require_sha(data, expected, name):
    if digest(data) != expected:
        raise ValueError('SOURCE_SHA_MISMATCH: '+name)


def load_original_stars(artifact_dir, manifest, name):
    entry = manifest['artifacts'][name]
    b64 = (artifact_dir / entry['file']).read_bytes()
    decoded = base64.b64decode(b64.strip(), validate=True)
    require_sha(decoded, entry['zip_sha256'], 'ORIGINAL_RNS_ZIP_'+name)
    with zipfile.ZipFile(io.BytesIO(decoded)) as z:
        all_names = set(z.namelist())
        if entry['json_name'] not in all_names:
            raise ValueError('missing original star JSON '+name)
        blob = z.read(entry['json_name'])
        require_sha(blob, entry['json_sha256'], 'ORIGINAL_RNS_JSON_'+name)
        record = json.loads(blob)
    if record['EOS'] != name or record['JESTER_source_commit'] != manifest['original_JESTER_commit']:
        raise ValueError('RNS SOURCE IDENTITY mismatch')
    stars = record['raw_C_rotating_stars']
    if len(stars) != entry['original_C_star_count']:
        raise ValueError('RNS star count changed')
    for star in stars:
        if not (np.isfinite(star['mass_msun']) and np.isfinite(star['central_energy_density_g_cm3']) and
                star['central_energy_density_g_cm3'] > 0 and star['solver_mode'].startswith('RNS_C_')):
            raise ValueError('malformed RNS star')
    return stars, record


def source_central_bracket(stars, target=REF_MASS):
    """Local interpolation only between authentic, increasing-density C stars.

    A high-density descending branch cannot be silently substituted; WFF1 has
    a tiny late post-peak irregularity, so examine only pre-peak adjacent
    pairs and insist that precisely one brackets the target mass.
    """
    ordered = sorted(stars, key=lambda s: s['central_energy_density_g_cm3'])
    peak = max(range(len(ordered)), key=lambda i: ordered[i]['mass_msun'])
    before_peak = ordered[:peak+1]
    pairs = [(a,b) for a,b in zip(before_peak[:-1], before_peak[1:])
             if a['mass_msun'] <= target <= b['mass_msun'] and a['mass_msun'] < b['mass_msun']]
    if len(pairs) != 1:
        raise ValueError('target mass requires exactly one authentic ascending C bracket')
    a,b=pairs[0]
    t = (target-a['mass_msun'])/(b['mass_msun']-a['mass_msun'])
    ec = a['central_energy_density_g_cm3']*(1-t) + b['central_energy_density_g_cm3']*t
    return ec, {'lower_msun':a['mass_msun'], 'upper_msun':b['mass_msun'],
                'lower_central_g_cm3':a['central_energy_density_g_cm3'],
                'upper_central_g_cm3':b['central_energy_density_g_cm3'],
                'interpolation_fraction':t}


def inspect_sample_arrays(p, e, cs2, central_g_cm3):
    p,e,cs2 = [np.asarray(x,dtype=np.float64) for x in (p,e,cs2)]
    if not (p.ndim==e.ndim==cs2.ndim==1 and len(p)==len(e)==len(cs2) and len(p)>=10):
        raise ValueError('malformed source arrays')
    if not all(np.isfinite(x).all() for x in (p,e,cs2)) or np.any(p<=0) or np.any(e<=0):
        raise ValueError('nonfinite / nonpositive source inputs')
    if not np.all(np.diff(p)>0):
        raise ValueError('source pressure grid is not increasing')
    if not 0 < central_g_cm3 < 1e17:
        raise ValueError('invalid C central density')
    ener_gcm3 = e*GEOM_E_TO_G_CM3
    low = ener_gcm3<=central_g_cm3
    if not np.any(low):
        raise ValueError('source EOS has no knots below actual C core')
    neg=np.flatnonzero(cs2<0)
    supr=np.flatnonzero(cs2>1)
    bad_e=np.flatnonzero(np.diff(e)<=0)
    def first_density(indices):return float(np.min(ener_gcm3[indices])) if len(indices) else None
    return {
        'source_knots':int(len(e)),
        'source_pressure_nonincreasing_edges':int(np.count_nonzero(np.diff(p)<=0)),
        'source_energy_nonincreasing_edges':int(len(bad_e)),
        'source_negative_cs2_knots':int(len(neg)),
        'source_superluminal_cs2_knots':int(len(supr)),
        'source_max_cs2':float(cs2.max()),
        'source_min_cs2':float(cs2.min()),
        'first_negative_cs2_density_g_cm3':first_density(neg),
        'first_superluminal_cs2_density_g_cm3':first_density(supr),
        'central_density_g_cm3':float(central_g_cm3),
        'sampled_knots_at_or_below_reference_core':int(np.count_nonzero(low)),
        'negative_cs2_knots_inside_reference_star_EOS_range':int(np.count_nonzero((cs2<0)&low)),
        'superluminal_cs2_knots_inside_reference_star_EOS_range':int(np.count_nonzero((cs2>1)&low)),
        'max_cs2_at_or_below_reference_core':float(cs2[low].max()),
        'reference_star_source_sampled_causality_gate': 'PASS_KNOTS_ONLY' if np.all((cs2[low]>=0)&(cs2[low]<=1)) and not np.any(np.diff(e)<=0) else 'FAIL_OR_UNRESOLVED',
        'global_source_sampled_causality_gate':'PASS_KNOTS_ONLY' if not len(neg) and not len(supr) and not len(bad_e) else 'FAIL_OR_UNRESOLVED',
    }


def scan(source_dir, artifacts_dir, source_manifest, artifact_manifest):
    mf=json.loads(Path(source_manifest).read_text())
    af=json.loads(Path(artifact_manifest).read_text())
    if mf['pinned_commit']!=af['original_JESTER_commit'] or set(mf['records'])!=set(EOS):
        raise ValueError('not the pinned original seven-source archive')
    result={'schema':'J0740_F75_SOURCE_PINNED_CENTRAL_CAUSALITY_KNOT_AUDIT_V1',
            'target_mass_msun':REF_MASS, 'source_JESTER_commit':mf['pinned_commit'],
            'source_RNS_commit':af['original_RNS_commit'],
            'method':'published original JESTER sampled LALSimulation p,e,cs2; genuine 346.536369 Hz RNS C source star density bracket at 2.073 Msun; no EOS changes',
            'status':'SAMPLED_THERMODYNAMIC_GATE_ONLY_NO_PHYSICAL_CERTIFICATION',
            'XPSI_source_native_photon_likelihood':'NOT_RUN',
            'global_EOS_physical_admissibility':'NOT_ESTABLISHED',
            'EOS_Bayesian_evidence':'NOT_RUN',
            'models':{}}
    for name in EOS:
        record=mf['records'][name]
        b=(Path(source_dir)/(name+'.npz')).read_bytes()
        require_sha(b,record['sha256'],'ORIGINAL_JESTER_NPZ_'+name)
        a=np.load(io.BytesIO(b),allow_pickle=False)
        if set(['p','e','cs2','eos_name','source'])-set(a.files):raise ValueError('NPZ missing required fields')
        if str(a['eos_name'])!=name or str(a['source'])!='LALSimulation':raise ValueError('wrong EOS source')
        stars, j=load_original_stars(Path(artifacts_dir),af,name)
        if j['source_original_npz_sha256']!=record['sha256']:
            raise ValueError('RNS star and NPZ source mismatch')
        core,bracket=source_central_bracket(stars)
        report=inspect_sample_arrays(a['p'],a['e'],a['cs2'],core)
        report['reference_mass_center_bracket']=bracket
        report['source_npz_sha256']=record['sha256']
        report['source_original_RNS_JSON_sha256']=af['artifacts'][name]['json_sha256']
        report['original_RNS_star_count']=len(stars)
        report['original_346Hz_RNS_C_source_solver_only']=True
        report['physical_certification']='NOT_ESTABLISHED'
        result['models'][name]=report
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source-dir',type=Path,required=True)
    p.add_argument('--artifacts-dir',type=Path,required=True)
    p.add_argument('--source-manifest',type=Path,required=True)
    p.add_argument('--artifact-manifest',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    report=scan(a.source_dir,a.artifacts_dir,a.source_manifest,a.artifact_manifest)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({n:{'central_e15_g_cm3':round(v['central_density_g_cm3']/1e15,6),
       'negative':v['negative_cs2_knots_inside_reference_star_EOS_range'],
       'superluminal':v['superluminal_cs2_knots_inside_reference_star_EOS_range'],
       'sample_gate':v['reference_star_source_sampled_causality_gate']}
       for n,v in report['models'].items()},indent=2))
    print('RESEARCH_STATE',report['status'])

if __name__=='__main__':main()