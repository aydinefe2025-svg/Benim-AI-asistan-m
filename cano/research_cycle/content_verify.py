"""Offline, fail-closed SHA-256 verification of actual source bytes.

The caller supplies bytes and claimed hashes. Matching a hash proves byte integrity
relative to that claim, NOT scientific accuracy or authenticity of the claim.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from source_queue import validate_record

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_BATCH = 100


def digest_file(path, max_bytes=MAX_FILE_BYTES):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing or symbolic-link source file')
    before = path.stat()
    if before.st_size > max_bytes:
        raise ValueError('source file exceeds size limit')
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('source file changed during hashing')
    return {'sha256': h.hexdigest(), 'bytes': after.st_size}


def verify_batch(records, root):
    """Validate the full batch before reporting any verified item."""
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('root must be directory')
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_BATCH:
        raise ValueError('expected 1-100 entries')
    seen = set()
    results = []
    for entry in records:
        if not isinstance(entry, dict) or set(entry) != {'record', 'file'}:
            raise ValueError('entry requires record and file')
        validated = validate_record(entry['record'])
        rel = entry['file']
        if not isinstance(rel, str) or not rel or '\\' in rel or '\x00' in rel:
            raise ValueError('invalid relative file path')
        p = Path(rel)
        if p.is_absolute() or any(part in ('..', '.') for part in p.parts):
            raise ValueError('unsafe path')
        target = root / p
        # Refuse symlinks in every component; no silent traversal outside root.
        cur = root
        for part in p.parts:
            cur = cur / part
            if cur.is_symlink():
                raise ValueError('symlink path rejected')
        resolved = target.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError('file outside root')
        if resolved in seen:
            raise ValueError('duplicate source file')
        seen.add(resolved)
        actual = digest_file(resolved)
        claimed = entry['record']['source_sha256']
        if actual['sha256'] != claimed:
            raise ValueError('SHA-256 mismatch: ' + rel)
        results.append({'file': rel, 'url': entry['record']['url'], 'sha256': actual['sha256'], 'bytes': actual['bytes'], 'integrity': 'matched_claim'})
    return {'verified': len(results), 'status': 'hash_matched_not_scientifically_validated', 'items': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch', type=Path, help='JSON list of {record, file}')
    parser.add_argument('root', type=Path, help='directory containing source files')
    args = parser.parse_args()
    if args.batch.is_symlink() or not args.batch.is_file() or args.batch.stat().st_size > 256 * 1024:
        parser.error('unsafe batch file')
    try:
        print(json.dumps(verify_batch(json.loads(args.batch.read_text('utf-8')), args.root), ensure_ascii=False, indent=2))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f'REJECTED: {exc}\n')

if __name__ == '__main__':
    main()