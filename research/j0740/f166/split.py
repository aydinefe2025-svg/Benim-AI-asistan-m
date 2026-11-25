"""Compare regenerated prefix, then emit ONLY disjoint suffix proposals."""
import sys,json,math,hashlib,zipfile,shutil
from pathlib import Path
SEEDS=(352001,352003,352007,352011)
MODELS={'MS1':16384,'MS1B':16384,'WFF1':8192,'WFF2':8192}
KEYS=('mass','radius','mass_u','logq_mass','logq_nuisance')
META=('model','seed','curve_sha256','mass_fraction','curve_zip_sha','support')
def close(a,b,tol):
 return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=tol
def prefix_matches(old,new):
 assert len(old['rows'])==4096 and len(new['rows'])==MODELS[old['model']]
 for k in META:
  if k in ('mass_fraction','support'):assert close(old[k],new[k],1e-12),k
  else:assert old[k]==new[k],k
 for i,(a,b) in enumerate(zip(old['rows'],new['rows'])):
  assert a['index']==b['index']==i and a['phase_positive']==b['phase_positive'],i
  for k in KEYS:assert close(a[k],b[k],1e-7 if k.startswith('logq') else 1e-9),(i,k)
  assert len(a['u'])==len(b['u'])==13 and all(close(x,y,1e-9) for x,y in zip(a['u'],b['u'])),i
def main():
 frozen,full,out=map(Path,sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
 assert hashlib.sha256(frozen.read_bytes()).hexdigest()=='c6c674a6fe54df64ae26a5df0ad94d734992cf60621c9aafc891719ae55084c2'
 with zipfile.ZipFile(frozen) as z:
  assert z.testzip() is None
  for model,n in MODELS.items():
   for seed in SEEDS:
    name='%s_%d.json'%(model,seed)
    oldbytes=z.read(next(x for x in z.namelist() if x.endswith('/'+name) or x==name))
    old=json.loads(oldbytes);new=json.loads((full/name).read_bytes())
    prefix_matches(old,new)
    (out/name).write_bytes(oldbytes)
    for offset in range(4096,n,4096):
     shard=dict(new,rows=[dict(row,index=i) for i,row in enumerate(new['rows'][offset:offset+4096])])
     assert len(shard['rows'])==4096
     (out/('%s_%d_%d.json'%(model,seed,offset))).write_text(json.dumps(shard,allow_nan=False))
    print('PREFIX_VERIFIED',model,seed,n,flush=True)
 shutil.copyfile(full/'fit_receipt.json',out/'fit_receipt.json')
if __name__=='__main__':main()
