#!/usr/bin/env python3
"""Independent SHA+formula audit of true F96 CI Einstein C numerical artifact.

No C reruns, no source reprior, no synthetic stars, no new photons.
Underlying original C/RNS event trace always survives; published derived receipt
is suitable for permanent GitHub Library archival.
"""
from __future__ import annotations
from pathlib import Path
from zipfile import ZipFile
import json,hashlib,math,os
import numpy as np
HERE=Path(__file__).resolve().parent
SOURCE=Path(os.getenv('F96_EVIDENCE_ZIP','/mnt/data/J0740_F96_REAL_C_18_stars_20261121.zip'))
F88=Path(os.getenv('F96_F88_ARCHIVE','/mnt/data/J0740_F88_original_C_RNS_archive.zip'))
F89=Path(os.getenv('F96_F89_ARCHIVE','/mnt/data/F89_native_existing_20261120.zip'))
DESIGN=Path(os.getenv('F96_FROZEN_DESIGN',str(HERE/'F96_source_locked_real_dual_grid_preflight_20261121.json')))
OUT=Path(os.getenv('F96_AUDIT_OUT',str(HERE/'F96_independent_actual_Einstein_C_18star_archive_receipt_20261121.json')))
SHA=lambda x:hashlib.sha256(x).hexdigest()
assert SOURCE.is_file() and F88.is_file() and F89.is_file()
with ZipFile(SOURCE) as z:
    members={n:z.read(n) for n in z.namelist()}
    claimed=json.loads(members['F96_SOURCE_C_EVIDENCE_SHA256_MANIFEST.json'])
    for name,metadata in claimed.items():
        assert name in members,('REAL_C_EVIDENCE_FILE_MISSING',name)
        assert metadata['bytes']==len(members[name]),('ACTUAL_C_BYTE_COUNT_DRIFT',name)
        assert metadata['sha256']==SHA(members[name]),('ACTUAL_C_SHA256_MISMATCH',name)
    report=json.loads(members['F96_REAL_two_grid_source_causal_fixedJ_extension.json'])
with ZipFile(F88) as z:
    old88=z.read('F88_REAL_two_grid_C_RNS.json');f88=json.loads(old88)
    original_eos=z.read('m.rns')
with ZipFile(F89) as z:
    old89=z.read('F89_ACTUAL_two_grid_fixed_J_local_screen.json');f89=json.loads(old89)
d=json.loads(DESIGN.read_text(encoding='utf8'))
assert report['F88_input_receipt_SHA256']==SHA(old88)==d['original_F88_real_C_two_grid_receipt_sha256']
assert report['F89_5x2_native_reference_SHA256']==SHA(old89)==d['original_F89_real_C_five_point_receipt_sha256']
assert report['real_source_rns_eos_SHA256']==SHA(original_eos)==d['original_F88_source_extended_eos_sha256']
assert report['original_C_compiler_binary_SHA256']==f88['binary_sha256']==d['original_F88_compiled_C_sha256']
assert report['source_original_Zenodo_SHA256']=='8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12'
assert report['status']=='TWO_GRID_ACTUAL_RNS_COMPLETE_CAUSAL_RANGE_DISCRETE_ONLY'
assert report['first_source_acausal_nodes']==24
J=d['canonical_identical_target_J_both_grids_cgs'];rho0=d['central_rho_common_reference_g_cm3'];upper=d['first_source_acausal_limit_g_cm3']
assert math.isclose(J,report['fixed_same_common_J_cgs'],rel_tol=1e-14)
assert math.isclose(rho0,report['central_rho_common_reference_g_cm3'],rel_tol=1e-14)
assert math.isclose(upper,report['first_source_acausal_rho_g_cm3'],rel_tol=1e-14)
assert report['density_grid_g_cm3']==d['same_absolute_density_both_grids_g_cm3']
assert len(report['density_grid_g_cm3'])==9
checks={};calls=0;mask=[]
for grid in ('151x301','201x401'):
    x=report['two_grid_native_results'][grid]
    stars=x['completed_actual_C_stars'];errors=x['errors']
    assert len(stars)==9 and not errors
    assert [p['source_point_index'] for p in stars]==list(range(9))
    assert x['native_C_calls_logged_in_trace']==sum(p['direct_C_evaluations'] for p in stars)
    for p,rho in zip(stars,report['density_grid_g_cm3']):
        assert p['real_solver_checked'] is True and p['measured_J_matches_common_target'] is True
        assert math.isclose(p['reported_rho_g_cm3'],rho,rel_tol=1.5e-4)
        assert p['reported_rho_g_cm3']<upper
        assert abs(p['J_measured_cgs']/J-1)<3e-5
    source_trace=members[f'F96_NATIVE_C_trace_{grid}.jsonl']
    assert SHA(source_trace)==x['trace_SHA256']
    trace=[json.loads(ln) for ln in source_trace.decode().splitlines()]
    assert len(trace)==x['native_C_calls_logged_in_trace']
    assert all('measured_M_Msun' in ln['record'] for ln in trace),('SOURCE_C_NOT_A_REAL_STELLAR_MODEL',grid)
    m=np.array([p['M_msun'] for p in stars]);rho=np.array([p['reported_rho_g_cm3'] for p in stars]);
    slopes=np.diff(m)/np.diff(rho/rho0)
    recorded=report['sampled_causal_derivative_signs'][grid]['interval_M_rho_slopes']
    assert len(slopes)==len(recorded)==8 and np.max(abs(slopes-np.array(recorded)))<1e-10
    assert np.all(slopes>0)
    checks[grid]={'actual_new_stars':9,'real_native_C_evaluations':len(trace),
                  'min_measured_fixedJ_M_rho_slope':float(np.min(slopes)),
                  'max_measured_fixedJ_M_rho_slope':float(np.max(slopes)),
                  'mass_at_first_rho_Msun':float(m[0]),'mass_at_last_rho_Msun':float(m[-1]),
                  'R_eq_at_first_km':stars[0]['R_eq_km'],'R_eq_at_last_km':stars[-1]['R_eq_km'],
                  'measured_frequency_at_first_hz':stars[0]['f_measured_hz'],
                  'measured_frequency_at_last_hz':stars[-1]['f_measured_hz'],
                  'max_J_relative_error':max(p['J_relative_error'] for p in stars),
                  'C_trace_SHA256':SHA(source_trace)}
    calls+=len(trace)
assert calls==205
pairs=[]
for x,y in zip(report['two_grid_native_results']['151x301']['completed_actual_C_stars'],report['two_grid_native_results']['201x401']['completed_actual_C_stars']):
    assert x['source_point_index']==y['source_point_index']
    pairs.append({'rho_g_cm3':x['reported_rho_g_cm3'],
                  'M_difference_Msun':x['M_msun']-y['M_msun'],
                  'R_difference_m':(x['R_eq_km']-y['R_eq_km'])*1000,
                  'J_relative_difference':x['J_measured_cgs']/y['J_measured_cgs']-1})
max_mass=max(abs(p['M_difference_Msun']) for p in pairs)
max_R=max(abs(p['R_difference_m']) for p in pairs)
max_J=max(abs(p['J_relative_difference']) for p in pairs)
assert max_mass<.001 and max_R<2 and max_J<3e-5
static=Path(os.getenv('F96_STATIC_SOURCE', '/mnt/data/j0740_f97/F97_new_source_causal_9point_real_static_GR_eigenmodes_20261121.json'))
source_delta=None
if static.is_file():
    e=json.loads(static.read_text())
    assert e['F95_interpolated_physically_causal_static_star_count']==7
    assert e['F95_interpolated_rejected_static_star_count']==2
    assert e['F96_new_rotating_scan_design_SHA256']==SHA(DESIGN.read_bytes())
    source_delta={'RNS_source_native_first_superluminal_energy_density_g_cm3':upper,
      'F95_logPCHIP_interpolated_first_superluminal_energy_density_g_cm3':e['F95_interpolation_first_causality_failure_rho_g_cm3'],
      'RNS_causal_knots_vs_PCHIP_model_do_not_imply_same_continuous_causality':True,
      'F95_causally_admissible_static_of_nine':7,
      'two_static_cases_acausal_under_F95_interpolation':2,
      'source_model_conditional_physical_interpretation':'F96 RNS stars solved native C source; continuous causality not independently proven. F95 PCHIP is a different interpolation.'}
result={'schema':'J0740_F96_INDEPENDENT_18_REAL_C_STARS_HASH_AND_MATH_AUDIT_V1',
 'status':'INDEPENDENTLY_VERIFIED_18_REAL_SOURCE_C_EINSTEIN_STARS_WITH_205_NATIVE_EVALS',
 'genuine_Github_Action_run_id':44940940031,'genuine_GitHub_artifact_id':14721697923,
 'original_real_F88_SHA256':SHA(old88),'original_real_F89_SHA256':SHA(old89),
 'original_publisher_Zenodo328_SHA256':d['original_328_APR_publisher_sha256'],
 'actual_F96_public_GitHub_artifact_ZIP_SHA256':SHA(SOURCE.read_bytes()),
 'actual_F96_native_C_JSON_SHA256':SHA(members['F96_REAL_two_grid_source_causal_fixedJ_extension.json']),
 'frozen_design_SHA256':SHA(DESIGN.read_bytes()),
 'eos_had_100_analytical_surface_extension_rows':True,
 'fixed_common_J_cgs':J,'first_source_acausal_rho_g_cm3':upper,
 'two_independent_meshes_real_native_C':checks,'actual_new_real_C_star_count':18,
 'real_C_model_function_calls':calls,'min_measured_J_mass_slope_both':min(x['min_measured_fixedJ_M_rho_slope'] for x in checks.values()),
 'no_observed_negative_sample_intervals_both_grids':True,
 'max_cross_grid_M_difference_Msun':max_mass,'max_cross_grid_R_eq_difference_m':max_R,
 'max_relative_J_cross_grid_difference':max_J,
 'per_matched_source_grid_point':pairs,
 'source_model_interpolation_warning':source_delta,
 'physically_valid_full_CONTINUUM_4d_fixedJ_branch':'NOT_PROVEN_BY_NINE_SAMPLES',
 'rotating_axisymmetric_DYNAMICAL_mode_eigenproblem':'NOT_RUN',
 'full_seven_EOS_native_XPSI_photon_Bayes':'NOT_RUN',
 'native_photon_calls_this_experiment':0,
 'not_repeated_existing_F89_old_10_stars':True,
 'no_12GB_salmi_archive_redownload':True}
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
print(json.dumps({'receipt':str(OUT),'sha256':SHA(OUT.read_bytes()),'new_stars':18,'actual_C_calls':calls,'min_slope':result['min_measured_J_mass_slope_both'],'max_R_grid_m':max_R,'max_M_grid_Msun':max_mass,'F95_separate_2_causality_fail_preserved':bool(source_delta)},ensure_ascii=False))
