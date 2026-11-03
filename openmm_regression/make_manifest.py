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
files['../../dist/'+wheel['file']] = wheel['sha256']
manifest.write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n')
print(f'Wrote {len(files)} hashes to {manifest}')
