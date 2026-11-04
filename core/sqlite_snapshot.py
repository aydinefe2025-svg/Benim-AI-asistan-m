"""Complete SQLite snapshots to a new local directory, without changing sources.

Supports task/session databases as well as research databases. Callers must
retain the manifest separately if they need an independently trusted digest.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


def _digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def _copy(source, target):
    with target.open('xb'):
        pass
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as src:
        if src.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Source SQLite integrity check failed')
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Snapshot SQLite integrity check failed')


def snapshot_directory(source: str | Path, destination: str | Path) -> dict:
    """Snapshot top-level .sqlite3/.db files; do not upload or delete anything."""
    source, destination = Path(source), Path(destination)
    if not source.is_dir():
        raise ValueError('Source database directory is missing')
    databases = sorted({*source.glob('*.sqlite3'), *source.glob('*.db')})
    if not databases or any(p.is_symlink() or not p.is_file() for p in databases):
        raise ValueError('No supported databases, or unsafe source file')
    destination.mkdir(parents=True, exist_ok=False)
    entries = []
    for database in databases:
        target = destination / database.name
        _copy(database, target)
        entries.append({'name': database.name, 'sha256': _digest(target)})
    manifest = {'schema': 'sqlite-directory-snapshot-v1', 'databases': entries}
    with (destination / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
    return {'status': 'verified', 'database_count': len(entries)}


def restore_directory(snapshot: str | Path, destination: str | Path) -> dict:
    """Verify every digest before restoring into a new directory only."""
    snapshot, destination = Path(snapshot), Path(destination)
    manifest_path = snapshot / 'manifest.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 1_000_000:
        raise ValueError('Invalid snapshot manifest')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or manifest.get('schema') != 'sqlite-directory-snapshot-v1':
        raise ValueError('Unsupported snapshot manifest')
    entries = manifest.get('databases')
    if not isinstance(entries, list) or not entries or len(entries) > 10000:
        raise ValueError('Invalid snapshot database collection')
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Invalid snapshot entry')
        name = entry.get('name')
        if (not isinstance(name, str) or not name or '/' in name or '\\' in name or
                ':' in name or Path(name).suffix not in {'.sqlite3', '.db'} or name in seen):
            raise ValueError('Unsafe or duplicate database name')
        seen.add(name)
        path = snapshot / name
        if path.is_symlink() or _digest(path) != entry.get('sha256'):
            raise ValueError('Snapshot digest mismatch')
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Snapshot integrity check failed')
    destination.mkdir(parents=True, exist_ok=False)
    for entry in entries:
        _copy(snapshot / entry['name'], destination / entry['name'])
    return {'status': 'verified', 'database_count': len(entries)}
