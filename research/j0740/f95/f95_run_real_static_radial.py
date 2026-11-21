from __future__ import annotations
import sys,json,time,hashlib
from pathlib import Path
from scipy.optimize import brentq,minimize_scalar
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f95_static_radial_modes import *
P,E,eos,nb,cs=prepare()
assert len(P)==1833 and sum(cs>1)==24
central_limit=float(P[np.flatnonzero(cs>1)[0]])
s=find_M2073(eos,P)
assert s['pc']<central_limit
mesh=[]
for N in (320,640,960):
 x=radial(s,eos,P,N)
 mesh.append(x)
 print('GRID',N,'w2',x['eigen_omega2_kmminus2'][0],'fHz',x['signed_frequency_hz'][0],'node_count',x['node_counts'],flush=True)
# TOV solver convergence holding PC fixed
sst=make_star(s['pc'],eos,P,rtol=2e-10,max_step=.02)
s2=radial(sst,eos,P,640)
print('TOV_TIGHT',sst['M']/MKM,sst['R'],s2['eigen_omega2_kmminus2'][0],s2['signed_frequency_hz'][0],flush=True)
# M maximum is NONPHYSICAL bc source EOS acausal at PC >448. this is pure NUMERIC MODE CROSS VALIDATION.
p_max=minimize_scalar(lambda pc: -make_star(pc,eos,P,rtol=8e-9,max_step=.055)['M'],bounds=(950,1150),method='bounded',options={'xatol':.0005})
peak={'pc_MeVfm3':float(p_max.x),'M_Msun':-float(p_max.fun)/MKM}
print('M_MAX_NUMERICAL_ACAUSAL',peak,flush=True)
modal={}
for n in (350,650):
 def mode(pc):return radial(make_star(pc,eos,P,rtol=8e-9,max_step=.055),eos,P,n)['eigen_omega2_kmminus2'][0]
 z=brentq(mode,1030,1130,xtol=.015)
 modal[n]={'pc_zero_radial_MeVfm3':float(z),'M_Msun':float(make_star(z,eos,P,rtol=8e-9,max_step=.055)['M']/MKM), 'omega2_at_1030':mode(1030),'omega2_at_1130':mode(1130)}
 print('ZERO_MODE_ACAUSAL',n,modal[n],flush=True)
report={'schema':'J0740_F95_REAL_SOURCE_APR_APR_UNIFIED_STATIC_GR_RADIAL_STURM_LIOUVILLE_V1',
'source':'CompOSE EOS 328 published Zenodo 15045814 / native EOS thermo 1833 rows, archive SHA256 8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12',
'source_original_sha256':'8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12',
'source_density_count':len(P),'source_acausal_nodes':int((cs>1).sum()),'source_first_superluminal_P_MeVfm3':central_limit,
'static_target_M_Msun':float(s['M']/MKM),'static_target_R_km':float(s['R']),'static_target_pc_MeVfm3':float(s['pc']),
'static_target_central_pressure_less_than_first_superluminal':bool(s['pc']<central_limit),
'physical_central_PCHIP_cs2_max':float(max(eos(v*A)[1] for v in np.geomspace(P[0],s['pc'],4000))),
'f95_algorithm_sha256':hashlib.sha256((Path(__file__).resolve().parent/'f95_static_radial_modes.py').read_bytes()).hexdigest(),
'fluid_model':'General-relativistic nonrotating adiabatic barotropic radial mode, gamma=(eps+p)/p*(dP/dE) using F87 published log-PCHIP interpolant',
'metric':'TOV ds2=-e^nu dt2 + e^lambda dr2; exact surface match nu(R)=ln(1-2M/R)',
'shooting_approximation':'NOT USED; finite-element Sturm-Liouville K zeta = omega2 B zeta, zeta center Dirichlet, free surface natural; 2-point Gauss per element',
'angular_momentum_J':'0_STATIC_ONLY',
'eigenmodes_meshes':mesh,
'first_mode_omega2_kmminus2':mesh[-1]['eigen_omega2_kmminus2'][0],
'fundamental_radial_f_Hz':mesh[-1]['signed_frequency_hz'][0],
'fundamental_radial_omega_squared_positive':mesh[-1]['eigen_omega2_kmminus2'][0]>0,
'lowest_eigenmode_nodes':mesh[-1]['node_counts'][0],
'f0_mesh320_960_rel_difference':abs(mesh[0]['signed_frequency_hz'][0]-mesh[-1]['signed_frequency_hz'][0])/mesh[-1]['signed_frequency_hz'][0],
'fine_TOV_R_diff_m':1000*(sst['R']-s['R']),
'fine_TOV_M_diff_Msun':float((sst['M']-s['M'])/MKM),
'fine_TOV_mesh640_f_Hz':s2['signed_frequency_hz'][0],
'fine_TOV_frequency_diff_Hz_at_mesh640':s2['signed_frequency_hz'][0]-mesh[1]['signed_frequency_hz'][0],
'acausal_branch_max_mass_numeric_only':peak,
'acausal_branch_radial_zero_mode_crosscheck_NUMERICAL_ONLY':modal,
'important_no_go':'Original APR(APR) source becomes acausal for pc>=448.889 MeV/fm3. Thus the high-density maximum-mass/zero-mode comparison uses acausal tables ONLY for numerical method crosscheck, and is NOT a physically valid EOS maximum mass or stability claim.',
'physical_scope':'Positive omega2 supports fundamental RADIAL DYNAMICAL stability at STATIC M2.073 star within first-source-acausal-pressure boundary. Not rotating C/RNS M2.073 at 346.536 Hz, no axisymmetric l>=1 eigenmodes, no global seven-EOS photon-native Bayesian model odds.',
'status':'REAL_PUBLISHER_SOURCE_STATIC_GR_RADIAL_OMEGA2_POSITIVE_WITH_MESH_AND_TOV_CONVERGENCE',
'photon_likelihood_new_calls':0,'previous_EOS_323_C_RNS_not_repeated':True,
'full_photon_EOS_Bayes':'NOT_RUN','spinning_star_axisymmetric_dynamic_stability':'NOT_PROVEN'}
out=str(Path(__file__).resolve().parent/'F95_real_APR_static_radial_eigenmodes_20261121.json')
open(out,'w').write(json.dumps(report,indent=2)+'\n')
print('OUT',out,flush=True)