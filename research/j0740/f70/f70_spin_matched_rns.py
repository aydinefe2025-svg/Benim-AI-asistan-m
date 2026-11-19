"""F70: repeat F68 346.536369-Hz rotating RNS on two spatial grids.

A radius difference between models with different *realized* spin is NOT a
pure spatial-convergence error. Compute direct, mass-and-frequency matched RNS
stars; never manufacture a corrected stellar radius by interpolation.
This applies ONLY to the F67/F68 alternate PCHIP EOS, not original MPA1 and
not the conditional F69 Fe56 low-pressure replacement.
"""
from __future__ import annotations
import argparse, hashlib, json, math, sys
from pathlib import Path
from scipy.optimize import brentq

TARGET_HZ = 346.536369
TARGETS = ('2.073', '2.250')
EOS_SHA = '5af6e77740c3af282d30918e69a1794dab84895092209ac850c1e2ed2945ac16'
MODEL = 'MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL'
SPIN_TOL = .005
MASS_TOL = 0.000005


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_f68(doc, grid, eos_sha=EOS_SHA):
    if doc.get('grid') != grid or doc.get('model') != MODEL or doc.get('not_original_MPA1') is not True:
        raise ValueError('F70_F68_MODEL_GRID_PROVENANCE_FAIL')
    if doc.get('rns_derived_table_sha256') != eos_sha:
        raise ValueError('F70_F68_EOS_SHA_DRIFT')
    if doc.get('original_seven_EOS_Bayes') != 'NOT_RUN':
        raise ValueError('F70_F68_POSTERIOR_LABEL_DRIFT')
    for key in TARGETS:
        a=doc['direct_C_stars'][key]['rotating']['star']
        s=doc['direct_C_stars'][key]['static']['star']
        if abs(a['mass_msun']-float(key))>.0015 or abs(a['spin_hz_reported']-TARGET_HZ)>.25 or s['spin_hz_reported']!=0:
            raise ValueError('F70_INCOMPLETE_F68_SOURCE_STARS')


def prior_diagnosis(coarse, fine):
    validate_f68(coarse,'151x301');validate_f68(fine,'201x401')
    out={}
    for key in TARGETS:
        a=coarse['direct_C_stars'][key]
        b=fine['direct_C_stars'][key]
        x=a['rotating']['star'];y=b['rotating']['star']
        out[key]={
            'F68_radius_mesh_difference_m':(y['radius_eq_km']-x['radius_eq_km'])*1000,
            'F68_frequency_difference_hz':y['spin_hz_reported']-x['spin_hz_reported'],
            'F68_coarse_spin_residual_hz':x['spin_hz_reported']-TARGET_HZ,
            'F68_fine_spin_residual_hz':y['spin_hz_reported']-TARGET_HZ,
            'F68_static_mesh_difference_m':(b['static']['star']['radius_eq_km']-a['static']['star']['radius_eq_km'])*1000,
            'F68_radius_is_pure_mesh_error':False,
            'reason':'F68 spinning RNS solutions have different realized frequencies; static does not.'
        }
    return out


def equal_spin_direct_model(binary, table, central_density, *, guess=None, max_calls=34):
    """Use direct RNS C -r equilibria; bracket frequency by axis ratio, not R interpolation.

    Every returned radius is computed by RNS itself. Existing root helper uses
    -s up to 0.25 Hz tolerance, so deliberately bypass that permissive path.
    """
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'rotating_gr'))
    from axis_ratio_rns import run_rns_at_ratio
    cache={}; calls=[]
    def eval_ratio(r):
        r=round(float(r),12)
        if r in cache:return cache[r]
        if not (0.76 <= r <= 1.0):raise ValueError('F70_UNSAFE_AXIS_RATIO')
        if len(cache)>=max_calls:raise RuntimeError('F70_SPIN_ROOT_CALL_LIMIT')
        o=run_rns_at_ratio(binary,table,central_density=central_density,ratio=r)
        cache[r]=o;calls.append({'r':r,'hz':o['spin_hz_reported'],'m':o['mass_msun']})
        return o
    if guess is not None and .78 < guess < .999:
        g=eval_ratio(guess)
        if abs(g['spin_hz_reported']-TARGET_HZ)<=SPIN_TOL:return g,calls
    # For RNS axis ratio, lower r usually means higher spin. Find a physical bracket.
    ratios=sorted(set([1.,.98,.96,.94,.92,.90,.88,.86,.84,.82,.80] +
                      ([guess, max(.76,guess-.004), min(1.,guess+.004)] if guess else [])),reverse=True)
    prev=None
    for ratio in ratios:
        try:model=eval_ratio(ratio)
        except (ValueError, RuntimeError, TimeoutError):
            continue
        hz=model['spin_hz_reported']
        if abs(hz-TARGET_HZ)<=SPIN_TOL:return model,calls
        if prev is not None and (prev[1]['spin_hz_reported']-TARGET_HZ)*(hz-TARGET_HZ)<0:
            high,low=prev[0],ratio
            try:
                root=brentq(lambda r: eval_ratio(r)['spin_hz_reported']-TARGET_HZ,
                            low,high,xtol=2e-11,rtol=1e-12,maxiter=25)
            except Exception as e:
                raise RuntimeError('F70_DIRECT_RNS_SPIN_ROOT_FAILED '+str(e)) from e
            model=eval_ratio(root)
            if abs(model['spin_hz_reported']-TARGET_HZ)>SPIN_TOL:
                raise ValueError('F70_FREQUENCY_NOT_MATCHED')
            return model,calls
        prev=(ratio,model)
    raise RuntimeError('F70_SPIN_CROSSING_NOT_FOUND')


def mass_spin_root(binary,table,mass_msun,seed_density,*,max_outer=7):
    """Solve true two-variable (M,spin) condition by nested direct C roots.

    A density root evaluates an actual C star at each iteration. Not an
    interpolated post-hoc radius. Outer secant is kept in ±3% of F68 seed.
    """
    results=[];ratio_guess=None
    def direct(ec):
        nonlocal ratio_guess
        if not (.97*seed_density<=ec<=1.03*seed_density):
            raise ValueError('F70_MASS_ROOT_OUTSIDE_PINNED_F68_LOCAL_BRANCH')
        st,trace=equal_spin_direct_model(binary,table,ec,guess=ratio_guess)
        ratio_guess=st['axis_ratio']
        item={'ec_g_cm3':ec,'m_msun':st['mass_msun'],'hz':st['spin_hz_reported'],
              'r_km':st['radius_eq_km'],'ratio':st['axis_ratio'],
              'rns_spin_direct_calls':len(trace)}
        results.append(item)
        return st
    s0=direct(seed_density)
    if abs(s0['mass_msun']-mass_msun)<=MASS_TOL:
        return s0,results
    # Secant from a ~0.1% density step, rather than multiple full-branch searches.
    step=0.001 if s0['mass_msun']<mass_msun else -0.001
    e_prev=seed_density;e_now=seed_density*(1+step)
    s_prev=s0;s_now=direct(e_now)
    for _ in range(max_outer-2):
        if abs(s_now['mass_msun']-mass_msun)<=MASS_TOL:
            return s_now,results
        dm=s_now['mass_msun']-s_prev['mass_msun']
        if abs(dm)<1e-9:raise RuntimeError('F70_MASS_SLOPE_TOO_SMALL')
        e_next=e_now+(mass_msun-s_now['mass_msun'])*(e_now-e_prev)/dm
        e_next=max(.972*seed_density,min(1.028*seed_density,e_next))
        if abs(e_next-e_now)<1e-11*seed_density:
            raise RuntimeError('F70_MASS_ROOT_STAGNATION')
        e_prev,s_prev=e_now,s_now
        e_now=e_next;s_now=direct(e_now)
    if abs(s_now['mass_msun']-mass_msun)>MASS_TOL:
        raise RuntimeError('F70_MASS_ROOT_NOT_CONVERGED')
    return s_now,results


def run(binary,table,old,grid,out):
    if sha(table)!=EOS_SHA:raise ValueError('F70_EOS_SOURCE_NOT_BYTE_IDENTICAL')
    validate_f68(old,grid if grid!='251x501' else '201x401')
    d={'schema':'F70_TRUE_DIRECT_RNS_EQUAL_MASS_EQUAL_SPIN_NUMERICAL_MESH_V1',
       'model':MODEL,'not_original_MPA1':True,'not_F69_Fe56_model':True,
       'target_spin_hz':TARGET_HZ,'spin_tolerance_hz':SPIN_TOL,
       'mass_tolerance_msun':MASS_TOL,'grid':grid,'rns_eos_sha256':EOS_SHA,
       'rns_binary_sha256':sha(binary),'stars':{},'status':'IN_PROGRESS',
       'EOS_Bayes':'NOT_RUN','microphysical_approval':'NOT_ESTABLISHED',
       'caveat':'Two spatial grids do not establish Richardson continuum convergence or physical EOS validation.'}
    out.parent.mkdir(exist_ok=True,parents=True)
    def save():out.write_text(json.dumps(d,indent=2,sort_keys=True,allow_nan=False)+'\n')
    save()
    for key in TARGETS:
        oldstar=old['direct_C_stars'][key]['rotating']['star']
        m=float(key)
        star,trace=mass_spin_root(binary,table,m,oldstar['central_energy_density_g_cm3'])
        if abs(star['spin_hz_reported']-TARGET_HZ)>SPIN_TOL or abs(star['mass_msun']-m)>MASS_TOL:
            raise ValueError('F70_DIRECT_C_TWO_CONSTRAINT_ROOT_FAIL')
        if star.get('solver_mode')!='RNS_C_AXIS_RATIO_DIRECT':
            raise ValueError('F70_NOT_A_DIRECT_AXIS_RATIO_C_STAR')
        d['stars'][key]={'actual_direct_RNS_C_model':{k:star[k] for k in ('mass_msun','spin_hz_reported','radius_eq_km','central_energy_density_g_cm3','axis_ratio','solver_mode')},
           'F68_unmatched_spin_radius_km':oldstar['radius_eq_km'],
           'F68_unmatched_spin_hz':oldstar['spin_hz_reported'],
           'within_grid_new_minus_F68_radius_m':(star['radius_eq_km']-oldstar['radius_eq_km'])*1000,
           'true_C_outer_iteration_trace':trace}
        save()
    d['status']='DIRECT_C_TRUE_MASS_AND_SPIN_MATCHED_TWO_STARS_NUMERICALLY_PASS'
    save();return d


def compare(coarse,fine,baseline):
    b=prior_diagnosis(baseline[0],baseline[1])
    if coarse['rns_eos_sha256']!=fine['rns_eos_sha256'] or coarse['grid']!='151x301' or fine['grid']!='201x401':
        raise ValueError('F70_TWO_MESH_IDENTITY_FAIL')
    r={'schema':'F70_DIRECT_C_MASS_SPIN_MATCHED_TWO_MESH_COMPARISON_V1',
       'source_eos_sha256':EOS_SHA,'target_hz':TARGET_HZ,'stars':{},
       'original_MPA1':'NOT_THIS_MODEL','physical_EOS_acceptance':'NOT_ESTABLISHED','seven_EOS_Bayes':'NOT_RUN'}
    for key in TARGETS:
        a=coarse['stars'][key]['actual_direct_RNS_C_model'];f=fine['stars'][key]['actual_direct_RNS_C_model']
        for x in (a,f):
            if abs(x['mass_msun']-float(key))>MASS_TOL or abs(x['spin_hz_reported']-TARGET_HZ)>SPIN_TOL:
                raise ValueError('F70_EITHER_GRID_MASS_SPIN_NOT_MATCHED')
        r['stars'][key]={'old_F68_spinning_two_mesh_radius_difference_m':b[key]['F68_radius_mesh_difference_m'],
                          'old_F68_two_mesh_frequency_difference_hz':b[key]['F68_frequency_difference_hz'],
                          'F70_true_C_mass_spin_matched_two_mesh_radius_difference_m':(f['radius_eq_km']-a['radius_eq_km'])*1000,
                          'F70_realized_frequency_difference_hz':f['spin_hz_reported']-a['spin_hz_reported'],
                          'F70_realized_mass_difference_msun':f['mass_msun']-a['mass_msun'],
                          'old_and_new_mesh_difference_delta_m':((f['radius_eq_km']-a['radius_eq_km'])*1000-b[key]['F68_radius_mesh_difference_m']),
                          'NOT_continuum_error_certified':True}
    r['status']='DIRECT_C_F70_COMPARISON_COMPLETE_TWO_MESH_ONLY';return r


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--binary',type=Path,required=True)
    ap.add_argument('--eos',type=Path,required=True);ap.add_argument('--f68',type=Path,required=True)
    ap.add_argument('--grid',choices=('151x301','201x401','251x501'),required=True)
    ap.add_argument('--out',type=Path,required=True)
    o=ap.parse_args();run(o.binary,o.eos,json.loads(o.f68.read_text()),o.grid,o.out)

if __name__=='__main__':main()