"""Package validated local native/Python fixes in a reinstallable Windows wheel."""
from pathlib import Path
import base64
import csv
import hashlib
import io
import json
import re
import zipfile

root = Path(__file__).resolve().parents[2]
summary = json.loads((Path(__file__).parent/'native_results/summary.json').read_text())
assert len(summary['tests']) == 5 and all(t['status'] == 'PASS' for t in summary['tests'])
assert not summary['plugin_errors']
site = root/'.venv/Lib/site-packages'
version = '8.6.1+local.20261103'
summary['python_package_version'] = version
info = f'openmm-{version}.dist-info'
entries = {}
for folder in ('openmm', 'simtk', 'OpenMM.libs', 'openmm-8.6.1.dist-info'):
    for p in (site/folder).rglob('*'):
        if not p.is_file() or '__pycache__' in p.parts or p.suffix in ('.pyc','.original','.stock'):
            continue
        name = p.relative_to(site).as_posix().replace('openmm-8.6.1.dist-info',info)
        if name.endswith('/RECORD'):
            continue
        entries[name] = p.read_bytes()
metadata = entries[info+'/METADATA'].decode().replace('\r\n','\n')
metadata, count = re.subn(r'(?m)^Version: 8\.6\.1\r?$',f'Version: {version}',metadata,count=1)
assert count == 1, 'Expected stock OpenMM 8.6.1 metadata'
entries[info+'/METADATA'] = metadata.encode()
if 'CUDA' in summary['platforms']:
    requirements=['nvidia-cuda-runtime-cu12==12.6.77',
                  'nvidia-cuda-nvrtc-cu12==12.6.85',
                  'nvidia-cufft-cu12==11.3.0.4','nvidia-nvjitlink-cu12==12.6.85']
    text=entries[info+'/METADATA'].decode()
    headers,body=text.split('\n\n',1)
    headers+='\n'+'\n'.join('Requires-Dist: '+r for r in requirements)
    entries[info+'/METADATA']=(headers+'\n\n'+body).encode()
entries['openmm/version.py'] = f'''# Locally validated build, not an upstream release.
import os
short_version = '{version}'
version = short_version
full_version = short_version
git_revision = '146a320f97bd4cd7319eaf94f58027d57f5abc7d+localfix'
release = True
openmm_library_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'OpenMM.libs', 'lib'))
'''.encode()
# Keep developer headers in sync with the locally compiled libraries.
for p in (root/'native-install/include').rglob('*'):
    if p.is_file():
        entries['OpenMM.libs/include/'+p.relative_to(root/'native-install/include').as_posix()] = p.read_bytes()
entries[info+'/LOCAL_BUILD.json'] = json.dumps(summary,indent=2).encode()
records = io.StringIO(newline='')
writer = csv.writer(records,lineterminator='\n')
for name, data in sorted(entries.items()):
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
    writer.writerow([name,'sha256='+digest,len(data)])
writer.writerow([info+'/RECORD','',''])
entries[info+'/RECORD'] = records.getvalue().encode()
dist = root/'dist'
dist.mkdir(exist_ok=True)
wheel = dist/f'openmm-{version}-cp312-cp312-win_amd64.whl'
with zipfile.ZipFile(wheel,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for name,data in sorted(entries.items()):
        z.writestr(name,data)
digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
(Path(__file__).parent/'native_results/wheel.json').write_text(json.dumps(dict(file=wheel.name,sha256=digest,bytes=wheel.stat().st_size),indent=2)+'\n')
print(wheel, digest)
