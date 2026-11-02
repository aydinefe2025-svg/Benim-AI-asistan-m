"""Validate final local parser patch and retain provenance."""
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
root=Path(__file__).resolve().parent
def run(name,args):
    r=subprocess.run([sys.executable,*args],cwd=root,capture_output=True,text=True,timeout=120)
    (root/'results'/f'{name}.log').write_text(r.stdout+'\nSTDERR:\n'+r.stderr)
    print(name,r.returncode,r.stdout,flush=True)
    return r.returncode
assert run('apply_fixes',['apply_mmcif_fixes.py'])==0
assert run('fixed_mmcif',['openmm_mmcif_roundtrip_regression.py','--output','results/fixed_mmcif.json'])==0
assert run('parser_extra',['parser_extra.py'])==0
run('pip_freeze',['-m','pip','freeze'])
status=run('summary',['summarize.py'])
files={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.name!='manifest.json'}
(root/'results'/'manifest.json').write_text(json.dumps(dict(created_utc=datetime.now(timezone.utc).isoformat(),sha256=files),indent=2))
raise SystemExit(status)
