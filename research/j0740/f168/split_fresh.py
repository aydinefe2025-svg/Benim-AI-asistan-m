import json,sys,hashlib,zipfile
from pathlib import Path
import numpy as np
MODELS=('MS1','MS1B')
SEEDS=(368001,368003,368007,368011)
N=16384

def main():
 full,old,out=map(Path,sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
 assert hashlib.sha256(old.read_bytes()).hexdigest()=='729a634eddf0b1637e22c0b4c3d0c62bfd0f03c37092a834566c2cfe2655124b'
 with zipfile.ZipFile(old) as z:
  assert z.testzip() is None
  for model in MODELS:
   previous=set()
   for name in z.namelist():
    if name.startswith(model+'_') and name.endswith('.json'):
     oldrows=json.loads(z.read(name))['rows'];previous.update(tuple([r['mass_u']]+r['u']) for r in oldrows)
   assert len(previous)==65536
   seen=set()
   for seed in SEEDS:
    d=json.loads((full/('%s_%d.json'%(model,seed))).read_text());assert d['model']==model and d['seed']==seed and len(d['rows'])==N and d['mass_fraction']==1.0
    for i,r in enumerate(d['rows']):
     assert r['index']==i and len(r['u'])==13 and all(0<x<1 for x in [r['mass_u']]+r['u']) and np.isfinite([r['logq_mass'],r['logq_nuisance']]).all()
     key=tuple([r['mass_u']]+r['u']);assert key not in previous and key not in seen;seen.add(key)
    for off in range(0,N,4096):
     shard=dict(d,rows=[dict(r,index=i) for i,r in enumerate(d['rows'][off:off+4096])]);(out/('%s_%d_%d.json'%(model,seed,off))).write_text(json.dumps(shard,allow_nan=False))
   assert len(seen)==65536
   print('F168_NEW_ROWS',model,len(seen),'NO_OLD_DUPLICATES',flush=True)
 (out/'fit_receipt.json').write_bytes((full/'fit_receipt.json').read_bytes())
if __name__=='__main__':main()
