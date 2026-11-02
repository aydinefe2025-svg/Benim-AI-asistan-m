"""Execute isolated reproducers, retaining baseline and fixed results."""
import json
import subprocess
import sys
from pathlib import Path
import openmm as mm

root=Path(__file__).resolve().parent
logs=root/'results'
logs.mkdir(exist_ok=True)
import openmm.app.pdbxfile as pdbx
source=Path(pdbx.__file__)
backup=source.with_suffix('.py.original')
if backup.exists():
    source.write_text(backup.read_text())
def run(name, *args):
    result=subprocess.run([sys.executable,*args],cwd=root,text=True,capture_output=True,timeout=240)
    (logs/(name+'.log')).write_text(result.stdout+'\nSTDERR:\n'+result.stderr)
    print(name, result.returncode, result.stdout[-1800:],result.stderr[-500:],flush=True)
    return result

run('pip_check','-m','pip','check')
run('installation','-m','openmm.testInstallation')
run('baseline_mmcif','openmm_mmcif_roundtrip_regression.py','--output','results/baseline_mmcif.json')
run('neighbor','neighbor_repro.py')
run('checkpoint','checkpoint_repro.py','OpenCL','single')
run('cpupme','cpupme_repro.py','OpenCL','single')
run('apply_fixes','apply_mmcif_fixes.py')
run('fixed_mmcif','openmm_mmcif_roundtrip_regression.py','--output','results/fixed_mmcif.json')
run('neighbor_retest','neighbor_repro.py')
run('checkpoint_retest','checkpoint_repro.py','OpenCL','single')
run('cpupme_retest','cpupme_repro.py','OpenCL','single')
(logs/'environment.json').write_text(json.dumps(dict(python=sys.version,openmm=mm.__version__,git_revision=mm.version.git_revision,platforms=[mm.Platform.getPlatform(i).getName() for i in range(mm.Platform.getNumPlatforms())],plugin_failures=list(mm.Platform.getPluginLoadFailures())),indent=2))
result=run('summary','summarize.py')
raise SystemExit(result.returncode)
