#!/usr/bin/env python3
"""Original EOS328 nine actual static TOV+radial eigenmode models on F96 C-scan densities.
Uses ORIGINAL F95 general-relativistic equations and publisher source, no mocks,
NOT a rotating mode calculation. Independent static cross-check to two-grid C work.
"""
import sys,json,math,hashlib
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq
ROOT=Path(__file__).resolve().parent
REF=(ROOT/'f95_reference') if (ROOT/'f95_reference/f95_static_radial_modes.py').is_file() else (ROOT.parent/'f95')
sys.path.insert(0,str(REF))
import f95_static_radial_modes as static
P,E,eos,nb,cs=static.prepare()
DESIGN=(ROOT/'F96_source_locked_real_dual_grid_preflight_20261121.json') if (ROOT/'F96_source_locked_real_dual_grid_preflight_20261121.json').is_file() else (ROOT.parent/'f96'/'F96_source_locked_real_dual_grid_preflight_20261121.json')
design=json.loads(DESIGN.read_text())
assert design['original_328_APR_publisher_sha256']=='8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12'
threshold=float(P[np.flatnonzero(cs>1)[0]])
eps_cgs_to_mev=(static.C**2)/static.MEVFM
logP_of_logE=PchipInterpolator(np.log(E),np.log(P),extrapolate=False)
smooth_pcrit=brentq(lambda pc:float(eos(pc*static.A)[1]-1),425.0,threshold)
smooth_rho_crit=float(eos(smooth_pcrit*static.A)[0]/static.A)*static.MEVFM/static.C**2
results=[]
for rho in design['same_absolute_density_both_grids_g_cm3']:
    energy_MeVFM=rho*eps_cgs_to_mev
    assert E[0]<energy_MeVFM<E[-1]
    pc=float(np.exp(logP_of_logE(np.log(energy_MeVFM))))
    assert pc<threshold,('SOURCE_ACAUSAL_SOURCE_CENTRAL_PRESSURE',pc,threshold)
    star=static.make_star(pc,eos,P)
    # Source matches 1% finite gradient from physical source source pressure;
    # only EOS interpolation is used, no ionization, rotation, or fake stars.
    cs0=float(eos(pc*static.A)[1])
    assert cs0>0
    interpolation_causal=bool(cs0<1 and pc<smooth_pcrit)
    radials=[]
    for N in (240,440):
        m=static.radial(star,eos,P,N)
        assert m['node_counts'][0]==0
        radials.append({'elements':N,'omega2_kmminus2':m['eigen_omega2_kmminus2'][0],
                        'fundamental_radial_Hz':m['signed_frequency_hz'][0],
                        'mode_nodes':m['node_counts']})
    results.append({'source_input_rho_g_cm3':rho,'source_interpolated_pressure_MeVfm3':pc,
                    'static_mass_Msun':star['M']/static.MKM,'static_R_km':star['R'],
                    'central_logPchip_dp_de_c2':cs0,
                    'F95_interpolated_static_model_causal':interpolation_causal,
                    'static_radial_modes':radials,
                    'nonrotating_only':True})
    print('F97_ACTUAL_STATIC_APR_SOURCE_CAUSAL_INTERPOLATION',json.dumps({'rho':rho,'pc':pc,
        'M':star['M']/static.MKM,'R':star['R'],'f0Hz440':radials[-1]['fundamental_radial_Hz'],
        'omega2_positive':radials[-1]['omega2_kmminus2']>0,'F95_static_causal':interpolation_causal}),flush=True)
assert len(results)==9
assert all(v['static_radial_modes'][-1]['omega2_kmminus2']>0 for v in results)
report={'schema':'J0740_F97_ORIGINAL_APR_SOURCE_CAUSAL_INTERPOLATION_9_DENSITIES_STATIC_GR_TOV_RADIAL_V1',
'status':'NINE_GENUINE_PUBLISHER_SOURCE_STATIC_RADIAL_STARS_COMPUTED_NOT_ROTATING_DYNAMICS',
'original_source_publisher_SHA256':design['original_328_APR_publisher_sha256'],
'F96_new_rotating_scan_design_SHA256':hashlib.sha256(DESIGN.read_bytes()).hexdigest(),
'F95_eigenmode_source_SHA256':hashlib.sha256((REF/'f95_static_radial_modes.py').read_bytes()).hexdigest(),
'original_source_first_superluminal_pressure_MeVfm3':threshold,
'native_first_acausal_source_secant_at_P_MeVfm3':float(P[np.where(np.diff(P)/np.diff(E)>1)[0][0]]),
'previous_source_secant_cs2':float((np.diff(P)/np.diff(E))[np.where(np.diff(P)/np.diff(E)>1)[0][0]-1]),
'new_physical_real_source_static_stars':results,'source_static_stars':9,'radial_eigenmode_numerical_solves':18,
'F95_interpolation_first_causality_failure_pressure_MeVfm3':smooth_pcrit,
'F95_interpolation_first_causality_failure_rho_g_cm3':smooth_rho_crit,
'F95_interpolated_physically_causal_static_star_count':sum(x['F95_interpolated_static_model_causal'] for x in results),
'F95_interpolated_rejected_static_star_count':sum(not x['F95_interpolated_static_model_causal'] for x in results),
'all_9_numeric_radial_fundamental_omega2_positive_but_some_acausal':True,
'physical_scope_warning':'Only models with F95 interpolated static dP/dE<1 on complete star segment may be physically interpreted; beyond P=437.59 MeV fm^-3 F95 log-PCHIP crosses 1 BEFORE first publisher native source row with cs2>1 at P=448.89, so high two modes are numerical only.',
'physical_scope':'Static J=0 GR barotropic adiabatic radial l=0 modes, publisher APR328 original source below first superluminal EOS point; not the 346.536369Hz rotating star, not axisymmetric modes',
'native_C_RNS_evaluations_in_this_STATIC_run':0,
'native_source_XPSI_photons_in_this_run':0,
'source_physical_eos_high_density_acausal_exception':'PRESERVED_24_NODES',
'rotating_star_dynamic_axisymmetric_stability':'NOT_RUN',
'full_seven_EOS_native_photon_Bayes':'NOT_RUN'}
out=ROOT/'F97_new_source_causal_9point_real_static_GR_eigenmodes_20261121.json'
out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n')
print('F97_ACTUAL_SOURCE_STATIC_FINAL',json.dumps({'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'n_stars':len(results),'causally_interpretable_stars':sum(x['F95_interpolated_static_model_causal'] for x in results),'min_f0Hz':min(v['static_radial_modes'][-1]['fundamental_radial_Hz'] for v in results),'max_f0Hz':max(v['static_radial_modes'][-1]['fundamental_radial_Hz'] for v in results)}),flush=True)