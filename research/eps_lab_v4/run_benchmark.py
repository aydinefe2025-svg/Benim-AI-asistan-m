import json,hashlib,pathlib
from pv_measured import audit,sparse_audit
p=pathlib.Path('benchmark.json');d=json.loads(p.read_bytes());out={'status':'PUBLISHED_EXPERIMENTAL_BENCHMARK_WITHIN_CURVE_HOLDOUT','source':d['source'],'source_git_blob_sha1':d['git_blob_sha1'],'extracted_json_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'devices':{},'limits':'Two historical published experimental curves. Alternating voltage samples held out, not independent device validation, measurement calibration or fault classification.'}
for k,x in d['devices'].items():
 out['devices'][k]=audit(x['V'],x['I']);out['devices'][k]['sparse']={str(n):sparse_audit(x['V'],x['I'],n) for n in (8,10,12)}; print(k,{n:v for n,v in out['devices'][k].items() if n not in ('points','sparse')},flush=True)
pathlib.Path('RESULT.json').write_text(json.dumps(out,indent=2,allow_nan=False))
