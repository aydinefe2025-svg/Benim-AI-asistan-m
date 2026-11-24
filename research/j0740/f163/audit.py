import sys,json,math,hashlib,zipfile
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
p,out,old,old2=map(Path,sys.argv[1:]);summary={}
manifest={'MS1-342001':'4f17748e814dee4b30c1c338a7635ab57fd5694e7cb02f7e09af1915a737de7b','MS1-342003':'126051360fd5401c66a3717067097e51d81e8d721ad4ab6634366164fce94675','MS1-342007':'9d70f372dec8b598503f210019c0857b8981629868b07afd33c2d699d3a82c95','MS1-342011':'a49ca67ef30beffb3383b7cfab6bbc666a7e4f58a790fbc53d754481e5dd1d83','MS1B-342001':'9270a38f6f5f13d639b4d5f15b9e44878f07ec02b1753aaf3c893dbae81a1f19','MS1B-342003':'957a9848b90d8f670bebea1ac21256ca682ffc0e3662f2c4cac15d20b60b2c53','MS1B-342007':'170b90013a21a36561ded5d5eead874ea2480d80ec87887376998b39aaa032cc','MS1B-342011':'b39c76410518129470c2836e87f1d599b29ebcefd9ab538eeb84073095fa092f'}
manifest2={'MS1-342001':'25f50a72fedf1717403c858e3cb26bc3ac35cb1bb1a25e2c797c66e62b60ebe1','MS1-342003':'ccda605afc0c76488c3055d09a26f55d2a930e506c4f9f232b9edee44bb7b38b','MS1-342007':'d3b12cb2e14f62e8722c5e70b3c1dec5130ce6bcfaf1a8fdcf7c165ea20a2b2a','MS1-342011':'5c7db977e0e0e83312ff398610e5c7794f8a6b35983f4cf4fbfbd8f61e398530','MS1B-342001':'7f2eea996ec146cf2432c38d7f33c72e286930fc505e3c7dcc5b5459fb9002a0','MS1B-342003':'17292ee7b870eecc88945f4095643d1aba1c967495cc2cb149185a0caa28e3e5','MS1B-342007':'29d09e452bb3af5fbee5471f2db4712b0cca16ce4778623a361e323172e4980c','MS1B-342011':'9adc6d4727c65d62d53342b2dd13f4acba9a3e49ec95cd52bd1bb4cc995f11b7'}
def stats(w):
 a=np.array(w);s=logsumexp(a);assert np.isfinite(s);q=np.exp(a-s)
 return dict(logZ=float(s-np.log(len(a))),ESS=float(1/(q@q)),maxW=float(q.max()))
for label in ('MS1','MS1B'):
 runs=[];allw=[]
 for seed in (342001,342003,342007,342011):
  key=label+'-'+str(seed); src=old/(key+'.zip');assert hashlib.sha256(src.read_bytes()).hexdigest()==manifest[key]
  with zipfile.ZipFile(src) as z:
   assert z.testzip() is None;previous=json.loads(z.read('native.json'))
  src2=old2/(key+'.zip');assert hashlib.sha256(src2.read_bytes()).hexdigest()==manifest2[key]
  with zipfile.ZipFile(src2) as z:
   assert z.testzip() is None;previous2=json.loads(z.read('native.json'))
  assert previous['model']==previous2['model']==label and previous['seed']==previous2['seed']==seed and previous['status']==previous2['status']=='COMPLETE'
  assert len(previous['rows'])==2048 and len(previous2['rows'])==6144
  assert previous2['old_proposal_sha256']==previous['proposal_sha256']
  rows=previous['rows']+previous2['rows'];hashes=[]
  for shard in (0,1):
   f=next(p.glob('**/F163-'+key+'-'+str(shard)+'/native.json'));d=json.loads(f.read_text())
   assert d['model']==label and d['seed']==seed and d['shard']==shard and len(d['rows'])==4096 and d['status']=='COMPLETE'
   assert d['old_proposal_sha256']==previous['proposal_sha256'] and d['f162_proposal_sha256']==previous2['proposal_sha256']
   assert d['curve_sha256']==previous2['curve_sha256']==previous['curve_sha256'] and d['support']==previous2['support']==previous['support']
   assert abs(d['reference_start']-previous2['reference_start'])<1e-6 and abs(d['reference_start']-d['reference_end'])<1e-6
   rows+=d['rows'];hashes.append(hashlib.sha256(f.read_bytes()).hexdigest())
  d['rows']=rows;assert len(rows)==16384
  w=[];phase=[]
  for i,r in enumerate(d['rows']):
   assert r['index']==i;phase.append(r['phase_positive'])
   if r['status']=='FINITE':
    v=r['logL']-r['logq_mass']-r['logq_nuisance']-math.log(d['support'])
    assert abs(v-r['logweight'])<1e-8 and abs(math.fsum(r['detectors'])-r['logL'])<1e-5
    w.append(v)
   else:assert r['status'] in ('PRIOR_REJECTED','MR_SUPPORT') and r['logweight'] is None;w.append(-math.inf)
  r=stats(w);r['half_logZ']=stats(w[:8192])['logZ'];r['phase_ESS']=[stats([v for v,b in zip(w,phase) if b==s])['ESS'] for s in (False,True)];r['seed']=seed;r['suffix_shas']=hashes;r['finite']=int(np.isfinite(w).sum());runs.append(r);allw.extend(w)
 gates=dict(ESS_each_ge100=all(r['ESS']>=100 for r in runs),maxW_le05=all(r['maxW']<=.05 for r in runs),phase_ESS_ge30=all(min(r['phase_ESS'])>=30 for r in runs),half_drift_le01=all(abs(r['logZ']-r['half_logZ'])<=.1 for r in runs),seed_range_le02=max(r['logZ'] for r in runs)-min(r['logZ'] for r in runs)<=.2)
 summary[label]=dict(pooled=stats(allw),runs=runs,gates=gates,accepted=all(gates.values()))
 print('F163_ACCEPTANCE',label,json.dumps(summary[label]),flush=True)
out.write_text(json.dumps(dict(status='NUMERICAL_WITNESS_ACCEPTANCE_ONLY',models=summary,limits='Same frozen Linux Sobol prefixes, 65536 old and 65536 new rows; not Windows prefix extension, not physical certification or final seven-EOS evidence.'),indent=2))
