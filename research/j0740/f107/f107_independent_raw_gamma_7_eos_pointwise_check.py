#!/usr/bin/env python3
"""Independent raw-Salmi-gamma 2D Gaussian conditional kernel at fixed M=2.073.
Not an X-PSI run and not independent full seven-model evidence.
"""
import json, math, hashlib, zipfile
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent/'native'
G=ROOT/'J07406620_amsterdam_gamma_NICERXMM_equal_weights_recent.npz'
R=ROOT/'F107_REAL_PUBLISHER_GAMMA_7_ORIGINAL_C_ROTATING_EOS_POSTERIOR_CONDITIONAL.json'
assert hashlib.sha256(G.read_bytes()).hexdigest()=='ad64ac47ea8b1c01034b72fb8b06160fba2e844974de41c7bf187cde12e1f698'
assert hashlib.sha256(R.read_bytes()).hexdigest()=='a18fbe1ce383a5155f0cb6dc151a88055fca5b49f6fb28403eef605494785087'
with np.load(G,allow_pickle=False) as z:
 m=np.asarray(z['mass'],float);r=np.asarray(z['radius'],float)
a=json.loads(R.read_text())
bw_m,bw_r=.035,.35
w=np.exp(-.5*((m-2.073)/bw_m)**2)
assert np.sum(w)>100
ref=a['bandwidth_sensitivity']['bandwidth_mass_0.035_radius_0.350']['scores']
compare={}
for model,item in ref.items():
 rr=item['radius_at_2p073_rotating_km']
 if rr is None:continue
 exact=float(np.dot(w,np.exp(-.5*((r-rr)/bw_r)**2))/(np.sum(w)*bw_r*math.sqrt(2*math.pi)))
 saved=float(item['observed_gamma_at_2p073_source_C_radius_per_km'])
 rel=abs(exact-saved)/max(exact,saved,1e-15)
 compare[model]={'independent_direct_100k_kernel_per_km':exact,'gridded_source_interpolated_conditional_per_km':saved,'relative_discrepancy':rel,'actual_C_rotating_radius_km':rr}
 if rel>.025:raise AssertionError((model,rel))
out={'schema':'J0740_F107_GENUINE_PUBLISHED_GAMMA_RAW_100K_INDEPENDENT_POINTWISE_7_ORIGINAL_RNS_C_RADIUS_CHECK',
     'gamma_native_source_sha256':hashlib.sha256(G.read_bytes()).hexdigest(),
     'F107_source_original_gamma_seven_C_JSON_SHA256':hashlib.sha256(R.read_bytes()).hexdigest(),
     'n_real_source_gamma':len(m),
     'reference_M_msun':2.073,
     'direct_gaussian_2d_conditional_kernel_not_source_F107_binned_method':True,
     'source_native_photon_Bayes':'NOT_RUN',
     'original_source_seven_EOS_physical_cert':'NOT_CERTIFIED',
     'model_comparisons':compare,
     'max_relative_7_source_discrepancy':max(x['relative_discrepancy'] for x in compare.values()),
     'passed':len(compare)==7}
p=Path(__file__).resolve().parent/'F107_INDEPENDENT_RAW_100K_GAMMA_SEVEN_SOURCE_C_POINT_AUDIT.json'
p.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps({'n':len(m),'max_discrepancy':out['max_relative_7_source_discrepancy'],'model_rel_errors':{x:round(y['relative_discrepancy'],5) for x,y in compare.items()},'sha256':hashlib.sha256(p.read_bytes()).hexdigest()},sort_keys=True))
