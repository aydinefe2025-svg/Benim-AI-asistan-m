from pathlib import Path
import json,hashlib,tarfile
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.interpolate import PchipInterpolator,RegularGridInterpolator

archive=Path(r'C:\Users\User\Downloads\mr_samples_and_contours.tar.gz')
evidence=Path(r'C:\Users\User\Documents\Codex\2026-11-08\codex-psr-j0740-6620-ara-tirmasina\evidence')
rns_file=evidence/'eos_small_sources/six_EOS_strict_causal_Steffen_RNS_sequences.json'
causal_file=evidence/'eos_small_sources/six_EOS_strict_causal_cut_verification.json'
lineage_file=evidence/'source_chain/published_chain_reconciliation.json'
v3_file=Path(r'D:\PSR_J0740+6620\work\MR_tailcorr_independent_v3_20261114\run_manifest.json')
def file_hash(path,kind='sha256'):
 h=hashlib.new(kind)
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 return h.hexdigest()
assert file_hash(archive,'md5')=='ca8e70eeca81feb71321f1a88a24f2f9'
with tarfile.open(archive,'r:gz') as tf:
 with tf.extractfile('mr_samples_and_contours/J0740_gamma_NxX_lp40k_se001_mrsamples_post_equal_weights.dat') as f:
  original=np.loadtxt(f,usecols=(0,1),dtype=float)
assert original.shape==(379669,2) and np.isfinite(original).all()
m,rad=original.T
rns=json.loads(rns_file.read_text());causal=json.loads(causal_file.read_text())
lineage=json.loads(lineage_file.read_text());v3=json.loads(v3_file.read_text())
assert lineage['runner_basename_matches_headline'] is False
assert v3['status']=='COMPLETE' and v3['overall_status']=='FAIL'
assert {d['eos'] for d in rns['models']}=={d['eos'] for d in causal['models']}
curves={}
model_physics={}
for model in rns['models']:
 name=model['eos'];comparison=next(x for x in causal['models'] if x['eos']==name)
 assert model['raw_source_sha256']==comparison['raw_source_sha256']
 assert model['original_raw_knots']==comparison['raw_knots_preserved']
 assert model['rns_table_rows']==comparison['rns_table_rows']
 assert model['causal_support_pass'] and comparison['causal_support_pass']
 rotating=next(x for x in model['curves'] if abs(x['spin_hz']-346.536369)<1.e-3)
 valid=[z for z in rotating['models'] if isinstance(z.get('mass_msun'),(float,int))]
 masses=np.array([z['mass_msun'] for z in valid],float)
 radii=np.array([z['radius_eq_km'] for z in valid],float)
 maxidx=int(np.argmax(masses));peakmass=float(masses[maxidx])
 model_physics[name]={'finite_grid_mass_peak_msun':peakmass,'target_root_recorded':model['target_2p073_rotating_star'] is not None,
     'causal_candidate_table_sha256':model['causal_table_sha256'],'original_EOS_source_sha256':model['raw_source_sha256'],
     'physical_status':'STRICT_CAUSAL_STEFFEN_MODIFIED_EOS_FINITE_GRID_ONLY'}
 if name not in ('MPA1','MS1','MS1B'):continue
 assert model['target_2p073_rotating_star'] is not None
 masses=masses[:maxidx+1];radii=radii[:maxidx+1]
 assert np.all(np.diff(masses)>0) and masses[0]<=1.88 and masses[-1]>=2.26
 curves[name]=(masses,radii)
assert len(curves)==3
edgesM=np.linspace(1.72,2.42,351);edgesR=np.linspace(8.0,16.2,411)
x=(edgesM[1:]+edgesM[:-1])/2
y=(edgesR[1:]+edgesR[:-1])/2
dx=float(x[1]-x[0]);dy=float(y[1]-y[0])
masks={'full':np.ones(len(m),dtype=bool),
       'even':np.arange(len(m))%2==0,
       'odd':np.arange(len(m))%2==1}
hist={}
for label,mask in masks.items():
 hist[label]=np.histogram2d(m[mask],rad[mask],bins=(edgesM,edgesR))[0]
 assert int(hist[label].sum())==int(np.sum(mask)),label
settings={'mass_windows':[(1.88,2.26),(1.94,2.21),(1.90,2.24)],
          'mass_radius_smoothing_km_and_msun':[(.01,.15),(.015,.25),(.02,.4)],
          'curve_interpolators':['pchip','linear'],
          'sample_partitions':['full','even','odd']}
rows=[]
for minmass,maxmass in settings['mass_windows']:
 gridmass=np.linspace(minmass,maxmass,301)
 for hmass,hradius in settings['mass_radius_smoothing_km_and_msun']:
  for split,counts in hist.items():
   smooth=gaussian_filter(counts,sigma=(hmass/dx,hradius/dy),mode='constant',truncate=4)
   smooth/=smooth.sum()*dx*dy
   density=RegularGridInterpolator((x,y),smooth,bounds_error=False,fill_value=0)
   for method in settings['curve_interpolators']:
    scores={}
    for label,(cm,cr) in curves.items():
     radius_curve=(PchipInterpolator(cm,cr)(gridmass) if method=='pchip'
                   else np.interp(gridmass,cm,cr))
     vals=density(np.column_stack((gridmass,radius_curve)))
     scores[label]=float(np.trapezoid(vals,gridmass))
    assert scores['MPA1']>0 and all(np.isfinite(list(scores.values())))
    rows.append({'mass_window_msun':[minmass,maxmass],'source_fraction_in_window':float(np.mean((m>=minmass)&(m<=maxmass))),
         'bandwidth_mass_msun':hmass,'bandwidth_radius_km':hradius,
         'partition':split,'interpolation':method,
         'overlap_index_per_km':scores,
         'relative_to_MPA1':{label:score/scores['MPA1'] for label,score in scores.items()}})
assert len(rows)==54 and all(z['relative_to_MPA1']['MS1']<1 and z['relative_to_MPA1']['MS1B']<1 for z in rows)
ranges={}
for model in ('MS1B','MS1'):
 values=[r['relative_to_MPA1'][model] for r in rows]
 ranges[model]={'range':[float(min(values)),float(max(values))],'median':float(np.median(values)),
                'all_54_less_than_MPA1':True}
main=next(z for z in rows if z['mass_window_msun']==[1.88,2.26]
          and z['bandwidth_mass_msun']==.015 and z['bandwidth_radius_km']==.25
          and z['partition']=='full' and z['interpolation']=='pchip')
report={'schema':'j0740_source_reproducible_conditional_curve_overlap_20261114_v1',
    'scientific_classification':'EXPLORATORY_DESCRIPTIVE_OBSERVATIONAL_CURVE_OVERLAP_NOT_BAYES_FACTOR',
    'published_source_md5':file_hash(archive,'md5'),
    'source_sample_count':len(original),
    'physical_inputs_sha256':{'rns_strict':file_hash(rns_file),'causal_original':file_hash(causal_file),
        'lineage':file_hash(lineage_file),'v3_fail':file_hash(v3_file)},
    'physics':model_physics,'curve_models':list(curves.keys()),'target_spin_hz':346.536369,
    'definition':'I_EOS = Integral_[Mmin,Mmax] published joint posterior p(M,R_EOS(M)) dM [km^-1]. Relative I/I_MPA1 only, not Bayes factors or EOS probabilities.',
    'smoothing':'2D histogram 350x410 then Gaussian filter, density renormalized; 301-point PCHIP or linear integral over stable sampled rising branch.',
    'sensitivity_settings':settings,'scenarios':rows,'baseline':main,
    'range_relative_to_MPA1':ranges,
    'scientific_limitations':['No exact native 15D EOS evidence, likelihood or population/selection integration was computed.',
       'The density overlap is on the observational posterior, not posterior divided by authenticated original run prior; do NOT call Bayes factor.',
       'The original posterior already contains radio timing mass information; do not multiply it again.',
       'Even and odd posterior subsamples can be correlated; comparisons are numerical sensitivity, not independent confidence bounds.',
       'Finite RNS curves use causal-modified Steffen EOS candidates, NOT original unchanged EOS tables.',
       'No continuously proven rotating stability at fixed angular momentum, continuum convergence or complete source domain.',
       'APR4_EPP original source causal-screened file absent; WFF1/WFF2/ENG finite grid does not reach target 2.073 M_sun.',
       'Original runner output basename yesMM vs publication noMM differs despite strong log-evidence numeric cross-match.',
       'v3 real source-nuisance heldout failed max-weight gate, cannot be promoted by any overlap score.'],
    'EOS_Bayes':'NOT_RUN','full_MR_nuisance_convergence':'NOT_ESTABLISHED',
    'new_photon_calls':0,'changed_original_sources':False}
selfpath=Path(__file__)
report['reproduction_script_sha256']=file_hash(selfpath)
serialized=(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n').encode('utf-8')
for loc in (Path(r'D:\PSR_J0740+6620\work\J0740_EOS_curve_overlap_sensitivity_20261114.json'),
           Path(r'C:\Users\User\AppData\Local\SentinelX\workspace\J0740_SOURCE_SUPPORT_READBACK_20261114\J0740_EOS_curve_overlap_sensitivity_20261114.json')):
 if loc.is_file():assert loc.read_bytes()==serialized,'report collision'
 else:
  with loc.open('xb') as f:f.write(serialized)
 assert loc.read_bytes()==serialized
print(json.dumps({'status':'PASS_54_OF_54','report_sha256':hashlib.sha256(serialized).hexdigest(),
    'script_sha256':file_hash(selfpath),'reported_ranges':ranges,'main':main['relative_to_MPA1'],
    'observed_mass_fraction':main['source_fraction_in_window'],'rows':len(rows),'EOS_Bayes':'NOT_RUN'},ensure_ascii=False))
