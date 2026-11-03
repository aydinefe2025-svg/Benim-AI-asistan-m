"""Install native artifacts into this project's venv; restore originals on validation failure."""
from pathlib import Path
import shutil, subprocess, sys, json, hashlib
root=Path(__file__).resolve().parents[2]
dest=root/'.venv/Lib/site-packages/OpenMM.libs'
source=root/'native-install'
backup=root/'native-stock-backup'
logs=root/'repo/openmm_regression/native_results'
logs.mkdir(exist_ok=True)
changed=[]
for file in (source/'lib').rglob('*'):
    if not file.is_file() or file.suffix.lower() not in ('.dll','.lib'): continue
    rel=file.relative_to(source)
    # The 8.6.1 wheel's SWIG extension was built against its RPMD plugin ABI.
    # Keep those wheel-matched DLLs; the upstream core build tree carries a
    # newer RPMD class layout and replacing them corrupts heap on destruction.
    if file.name.startswith('OpenMMRPMD'):
        continue
    target=dest/rel
    save=backup/rel
    if target.exists() and not save.exists():
        save.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,save)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(file,target)
    changed.append(str(rel))
assert any(x.endswith('OpenMM.dll') for x in changed)
env=dict(__import__('os').environ)
env['OPENMM_PLUGIN_DIR']=str(dest/'lib/plugins')
commands=[('installation',['-m','openmm.testInstallation']),('regressions',[str(root/'repo/openmm_regression/test_native.py')]),('parser_extra',[str(root/'repo/openmm_regression/parser_extra.py')])]
failed=False
for label,args in commands:
    p=subprocess.run([sys.executable,'-u',*args],cwd=root/'repo/openmm_regression',env=env,text=True,capture_output=True,timeout=300)
    (logs/(label+'.log')).write_text(p.stdout+'\nSTDERR:\n'+p.stderr)
    print(label,p.returncode,p.stdout[-4000:],p.stderr[-1000:],flush=True)
    failed |= p.returncode!=0
if failed:
    for rel in changed:
        saved=backup/rel
        if saved.exists():
            shutil.copy2(saved,dest/rel)
        else:
            (dest/rel).unlink(missing_ok=True)
    print('Validation failed: original native libraries restored')
    raise SystemExit(1)
manifest={rel:hashlib.sha256((dest/rel).read_bytes()).hexdigest() for rel in changed}
(logs/'installed_libraries.json').write_text(json.dumps(manifest,indent=2))
print('Native install and all scientific assertions PASS')

