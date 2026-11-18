"""F56 audit original source-native WFF1 versus F42 modified WFF1, NOT EOS Bayes.

This is a *provenance and physical-admissibility audit*, not an RNS run.
F42 changes e(p) one-sided at fixed p, imposes c_s²<=0.99 and a cold-gas
surface; F55 established numerical convergence only for that NEW candidate.
We compare the exact original JESTER arrays to F42 at identical pressure
and inspect source-native cs2, sampled first-law and J0740 F53 center overlap.
Source-native WFF1 may fail physical gates, but the diagnostic can finish:
a successful audit != a passing original nuclear EOS.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,sys,zipfile
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'f42'))
sys.path.insert(0,str(HERE.parent/'rotating_gr'))
from f42_causal_firstlaw_candidates import Candidate,C,G
from source_eos_causality import profile as native_profile
from source_native_global_gate import audit_arrays

ORIG_SHA='119b8a25435faeddf00f5d3638f3ff2ff00283ce60caacc24cc37c6e2e030ed3'
F53_ZIP_SHA='e35a52b02745d596cdea93427e15d5f7eb1e52c6f591fb21eb61501d57de2ae7'
F55_ZIP_SHA='2285023c17b7ce8eb7bf9d6ec07dfdd9a18fef64db0dca251ed37bcd487901a4'
F55_RESULT_SHA='ef2735fe9f99e46f682946fa2c9294fe2218b43bd68b401ce0311d20e679555b'
TARGET_EC_E15=2.900
CAP=.99
ALPHA=.6
SOURCE_LIFT_REPRODUCE_REL=2e-10
NPZ_COMMIT='e6768650ce992abfd1153a6833857572fe5cd230'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def load_source(original,f53zip,f55zip):
    if sha(original)!=ORIG_SHA or sha(f53zip)!=F53_ZIP_SHA or sha(f55zip)!=F55_ZIP_SHA:
        raise ValueError('F56_PINNED_SOURCE_F53_F55_SHA_DRIFT')
    with np.load(original,allow_pickle=False) as z:
        required={'e','p','cs2','n','h','masses_EOS','radii_EOS'}
        if not required.issubset(set(z.files)):
            raise ValueError('F56_NATIVE_SOURCE_KEYS_INCOMPLETE')
        arrays={k:np.asarray(z[k],float) for k in required}
    with zipfile.ZipFile(f53zip) as z:
        if z.testzip() is not None:
            raise ValueError('F56_F53_CI_ZIP_CRC_FAIL')
        ref=json.loads(z.read('F53_WFF1_direct_C_constant_J_stars.json'))
        if ref['status']!='PASS_SAMPLED_CONSTANT_J_TURNING_DIAGNOSTIC_NOT_GLOBAL_STABILITY':
            raise ValueError('F56_F53_DOES_NOT_HAVE_PROVEN_ORIGINAL_NEW_C_ROOTS')
        good=[s for s in ref['direct_C_constant_J_stars']
              if s['status']=='DIRECT_C_FIXED_J_PASS'
              and abs(s['ec_g_cm3']/1e15-TARGET_EC_E15)<1e-7]
        if len(good)!=1:
            raise ValueError('F56_F53_UNIQUE_REAL_C_REFERENCE_MISSING')
        anchor=good[0]
    with zipfile.ZipFile(f55zip) as z:
        if z.testzip() is not None:
            raise ValueError('F56_F55_CI_ZIP_CRC_FAIL')
        raw=z.read('F55_WFF1_original_source_EOS_knots_C_GR.json')
        if hashlib.sha256(raw).hexdigest()!=F55_RESULT_SHA:
            raise ValueError('F56_F55_SCIENTIFIC_JSON_SHA_DRIFT')
        f55=json.loads(raw)
        if f55['status']!='PASS_THREE_EOS_KNOT_SENSITIVITIES_NOT_PHYSICAL_EOS':
            raise ValueError('F56_F55_NUMERIC_KNOT_SOURCE_NOT_VERIFIED')
        if f55['source_original_WFF1_npz_sha256']!=ORIG_SHA:
            raise ValueError('F56_ORIGINAL_EOS_PROVENANCE_DRIFT')
    return arrays,anchor,ref,f55


def compare_at_pressure(p,e,cs2,candidate,center_e):
    """Equal-pressure native/candidate comparison, not an original GR star."""
    if not (p.ndim==e.ndim==cs2.ndim==1 and p.shape==e.shape==cs2.shape
            and len(p)>20 and np.isfinite(p).all() and np.isfinite(e).all()
            and np.isfinite(cs2).all() and np.all(p>0) and np.all(e>0)
            and np.all(np.diff(p)>0)):
        raise ValueError('F56_ORIGINAL_PRESSURE_GRID_INVALID')
    if not (candidate.e[0]<center_e<candidate.e[-1]):
        raise ValueError('F56_REFERENCE_F53_CENTER_OUTSIDE_F42_EOS')
    p_at_center=float(np.interp(center_e,candidate.e,candidate.p))
    if not p[0]<=p_at_center<=p[-1]:
        raise ValueError('F56_CENTER_PRESSURE_OUTSIDE_ORIGINAL_SOURCE')
    original_e_center_p=float(np.interp(p_at_center,p,e))
    candidate_e_center_p=float(candidate.values(np.array([p_at_center]))[0][0])
    if not abs(candidate_e_center_p/center_e-1)<2e-9:
        raise ValueError('F56_CANDIDATE_CENTER_PRESSURE_INVERSION_FAILED')
    source_e_at_p=original_e_center_p
    source_cs_at_p=float(np.interp(np.log(p_at_center),np.log(p),cs2))
    frac=(candidate.e-e)/e
    changed=frac>1e-13
    within=candidate.e<=center_e
    native_within=e<=center_e
    born=np.flatnonzero(changed)
    native_super=np.flatnonzero(cs2>1+1e-8)
    native_negative=np.flatnonzero(cs2<0)
    de=np.diff(e);dp=np.diff(p)
    source_secants=np.divide(dp,de,out=np.full_like(dp,np.nan),where=de>0)
    invalid=np.flatnonzero(de<=0)
    candidate_secants=dp/np.diff(candidate.e)
    return {
        'F53_anchor_central_e15_g_cm3':center_e*C*C/G*1e-3/1e15,
        'F53_anchor_original_star_EOS':'F42_MODIFIED_WFF1_NOT_ORIGINAL_WFF1',
        'equal_pressure_comparison_not_equal_mass_or_original_star':True,
        'p_at_F53_modified_star_center_geom_m_inv2':p_at_center,
        'energy_density_modified_at_same_p_geom_m_inv2':candidate_e_center_p,
        'energy_density_unmodified_native_at_same_p_geom_m_inv2':source_e_at_p,
        'native_minus_modified_energy_fraction_at_equal_pressure':source_e_at_p/candidate_e_center_p-1,
        'native_cs2_over_c2_logp_interpolated_same_pressure':source_cs_at_p,
        'source_node_count':int(len(p)),
        'candidate_source_changed_nodes_global':int(changed.sum()),
        'candidate_source_changed_nodes_below_modified_anchor_energy':int((changed&within).sum()),
        'candidate_source_eligible_nodes_below_modified_anchor_energy':int(within.sum()),
        'first_modified_source_index':int(born[0]) if len(born) else None,
        'first_modified_source_pressure_geom':float(p[born[0]]) if len(born) else None,
        'max_fractional_energy_lift_global':float(frac.max()),
        'max_fractional_energy_lift_below_modified_star_center':
            float(frac[within].max()) if within.any() else None,
        'native_cs2_superluminal_count_global':int(len(native_super)),
        'native_cs2_negative_count_global':int(len(native_negative)),
        'native_cs2_superluminal_below_F53_energy_threshold':
            int(((cs2>1+1e-8)&native_within).sum()),
        'native_cs2_negative_below_F53_energy_threshold':
            int(((cs2<0)&native_within).sum()),
        'native_cs2_max':float(cs2.max()),
        'native_cs2_min':float(cs2.min()),
        'native_first_superluminal_index':int(native_super[0]) if len(native_super) else None,
        'native_first_superluminal_density_g_cm3':
            float(e[native_super[0]]*C*C/G*1e-3) if len(native_super) else None,
        'raw_native_energy_nonincreasing_interval_count':int(len(invalid)),
        'raw_native_secant_noncausal_positive_over_one_count':
            int(np.count_nonzero(np.isfinite(source_secants)&(source_secants>1+1e-8))),
        'F42_candidate_max_source_pressure_interval_cs2':float(candidate_secants.max()),
        'F42_candidate_all_source_interval_cs2_positive_causal':
            bool(np.all(candidate_secants>0)&np.all(candidate_secants<=CAP*(1+3e-11))),
        'native_original_GR_stellar_mass_at_same_pressure':'NOT_COMPUTED',
        'native_original_fixed_J_star_at_same_density':'NOT_COMPUTED',
    }


def run(original,f53zip,f55zip,out,detail):
    arrays,anchor,old53,old55=load_source(original,f53zip,f55zip)
    p,e,cs2,n,h=[arrays[k] for k in ('p','e','cs2','n','h')]
    c=Candidate(p,e,cap=CAP,alpha=ALPHA)
    center=float(anchor['ec_g_cm3']*G*1e3/C**2)
    diag=compare_at_pressure(p,e,cs2,c,center)
    if abs(diag['max_fractional_energy_lift_global'] -
           old55['source_original_max_energy_lift_fraction'])>SOURCE_LIFT_REPRODUCE_REL:
        raise ValueError('F56_F55_F42_SOURCE_LIFT_NOT_REPRODUCIBLE')
    original_profile=native_profile(e,p,cs2)
    try:
        native_firstlaw=audit_arrays(p,e,n,h,cs2,center_e=center)
        native_firstlaw_status='SOURCE_SAMPLED_AUDIT_EXECUTED'
    except Exception as exc:
        native_firstlaw={'error':type(exc).__name__+': '+str(exc)[:400]}
        native_firstlaw_status='SOURCE_SAMPLED_AUDIT_FAILED_UNCERTIFIED'
    mass=arrays['masses_EOS'];radius=arrays['radii_EOS']
    if not (mass.ndim==radius.ndim==1 and len(mass)>20 and mass.shape==radius.shape
            and np.isfinite(mass).all() and np.isfinite(radius).all()
            and np.all(mass>0) and np.all(radius>0)):
        raise ValueError('F56_NATIVE_STATIC_SOURCE_MR_INVALID')
    max_index=int(np.argmax(mass))
    native_issue=(original_profile['status']!='SOURCE_NATIVE_CS2_SCREEN_PASS'
                  or diag['raw_native_energy_nonincreasing_interval_count']>0)
    report={
        'schema':'J0740_F56_SOURCE_NATIVE_WFF1_VERSUS_NEW_F42_LIFT_AUDIT_V1',
        'status':'SOURCE_LOCKED_PHYSICAL_ADMISSIBILITY_AUDIT_COMPLETED_NOT_NEW_RNS',
        'source_JESTER_commit':NPZ_COMMIT,
        'source_original_WFF1_npz_sha256':sha(original),
        'F53_direct_WFF1_modified_C_zip_sha256':sha(f53zip),
        'F55_EOS_knot_sensitivity_zip_sha256':sha(f55zip),
        'F53_modified_real_C_reference':{k:anchor[k] for k in
             ('ec_g_cm3','mass_msun','radius_eq_km','spin_hz','J_cgs')},
        'original_source_native_cs2_profile':original_profile,
        'original_source_firstlaw_interval_screen_status':native_firstlaw_status,
        'original_source_firstlaw_interval_screen':native_firstlaw,
        'native_static_JESTER_reference':{
            'max_tabulated_static_mass_msun':float(mass[max_index]),
            'radius_at_max_tabulated_static_mass_km':float(radius[max_index]),
            'source_static_MR_array_points':int(len(mass)),
            'causal_and_mass_support_validated':'NOT_ESTABLISHED',
            'does_not_prove_spin346Hz_or_fixedJ':'TRUE'},
        'F42_energy_lift_and_anchor_pressure':diag,
        'reconstructed_candidate_parameters':{'causal_cs2_cap':CAP,'cold_gas_alpha':ALPHA,
          'low_pressure_extrapolation':'ASSUMED','bare_baryon_mu0':'ASSUMED'},
        'modified_candidate_vs_native_original_same_EOS':False,
        'source_native_physical_admissibility':(
          'SOURCE_NATIVE_HAS_CAUSAL_OR_E_MONOTONICITY_WARNINGS'
          if native_issue else 'SAMPLED_SOURCE_SCREEN_NO_OBVIOUS_CAUSAL_FAILURE_NOT_GLOBAL_PROOF'),
        'native_unmodified_model_physically_certified':False,
        'new_GR_RNS_star_solutions':0,
        'new_source_native_XPSI_photon_level_Bayes':'NOT_RUN',
        'new_seven_model_Bayes':'NOT_RUN',
        'scope_caveat':('Original/native cs2 and equal-pressure EOS comparison alone are not rotating-star '
                       'solutions or stability evidence. Compare exact tables; do not transfer F53 radii '
                       'or maximum masses to the unmodified original WFF1.'),
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n')
    detail.parent.mkdir(parents=True,exist_ok=True)
    with detail.open('w',encoding='utf8',newline='') as f:
        w=csv.writer(f)
        w.writerow(['source_index','p_geometric_m_inv2','native_e_geometric_m_inv2',
                    'modified_F42_e_geometric_m_inv2','fractional_e_lift',
                    'native_analytic_cs2','modified_F42_interval_secant_cs2',
                    'native_rho_g_cm3','modified_F42_rho_g_cm3'])
        for i in range(len(p)):
            speed=CAP if i==len(p)-1 else float((p[i+1]-p[i])/(c.e[i+1]-c.e[i]))
            w.writerow([i,repr(float(p[i])),repr(float(e[i])),repr(float(c.e[i])),
                        repr(float(c.e[i]/e[i]-1)),repr(float(cs2[i])),repr(speed),
                        repr(float(e[i]*C*C/G*1e-3)),repr(float(c.e[i]*C*C/G*1e-3))])
    print(json.dumps({'status':report['status'],
                       'native_status':report['source_native_physical_admissibility'],
                       'native_cs2_max':diag['native_cs2_max'],
                       'native_cs2_over1':diag['native_cs2_superluminal_count_global'],
                       'lift_max_fraction':diag['max_fractional_energy_lift_global'],
                       'modified_nodes':diag['candidate_source_changed_nodes_global'],
                       'native_vs_candidate_center_e_fraction':
                           diag['native_minus_modified_energy_fraction_at_equal_pressure']},sort_keys=True))
    return report


def main():
    p=argparse.ArgumentParser()
    for key in ('npz','f53','f55','out','detail'):
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    run(a.npz,a.f53,a.f55,a.out,a.detail)

if __name__=='__main__':main()
