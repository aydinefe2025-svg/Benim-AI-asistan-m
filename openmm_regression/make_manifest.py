"""Write SHA-256 hashes for the reproducible source and result artifacts."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent
manifest = root/'native_results/manifest.json'
files = {}
for path in sorted(root.rglob('*')):
    if not path.is_file() or path == manifest or '__pycache__' in path.parts or path.suffix == '.pyc':
        continue
    files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
wheel = json.loads((root/'native_results/wheel.json').read_text())
dist = root.parent.parent/'dist'
for artifact in sorted(dist.glob('*.whl')):
    files['../../dist/'+artifact.name] = hashlib.sha256(artifact.read_bytes()).hexdigest()
if wheel['file'] not in {Path(name).name for name in files if name.startswith('../../dist/')}:
    raise FileNotFoundError(f"Verified OpenMM wheel is absent from {dist}: {wheel['file']}")
wheel_path = dist/wheel['file']
if hashlib.sha256(wheel_path.read_bytes()).hexdigest() != wheel['sha256']:
    raise ValueError(f"SHA-256 mismatch for verified OpenMM wheel: {wheel_path}")
manifest.write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n')
print(f'Wrote {len(files)} hashes to {manifest}')
