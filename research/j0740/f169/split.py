import hashlib,json,sys,zipfile
from pathlib import Path
import numpy as np
full,old,prev,out=map(Path,sys.argv[1:]);out.mkdir(exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(old.read_bytes())=='729a634eddf0b1637e22c0b4c3d0c62bfd0f03c37092a834566c2cfe2655124b'
assert sha(prev.read_bytes())=='0ef0c821ef17c270643ced027e3f109696d1d93786c4ae0e7c27ef4c4fc05987'
key=lambda r:tuple([r['mass_u']]+r['u'])
with zipfile.ZipFile(old) as z,zipfile.ZipFile(prev) as f:
 assert z.testzip() is None and f.testzip() is None
 earlier={key(r) for n in z.namelist() if n.startswith('MS1_') and n.endswith('.json') for r in json.loads(z.read(n))['rows']}
 assert len(earlier)==65536
 seen=set()
 for seed in (368001,368003,368007,368011):
  d=json.loads((full/f'MS1_{seed}.json').read_text());assert d['model']=='MS1' and d['seed']==seed and len(d['rows'])==32768
  for off in range(0,32768,4096):
   name=f'MS1_{seed}_{off}.json';shard=dict(d,rows=[dict(r,index=i) for i,r in enumerate(d['rows'][off:off+4096])])
   for r in shard['rows']:
    k=key(r);assert k not in earlier and k not in seen;seen.add(k)
   if off<16384:
    raw=f.read(name);v=json.loads(raw);assert v==shard,name
    (out/name).write_bytes(raw)
   else:(out/name).write_text(json.dumps(shard,allow_nan=False))
 assert len(seen)==131072
(out/'fit_receipt.json').write_bytes((full/'fit_receipt.json').read_bytes())
print('F169 exact 65536 prefix rows preserved; 65536 disjoint new rows',flush=True)
