"""Read-only scientific data intake: inspect local directories or ZIP files, never extract."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile

MAX_FILES = 10000
MAX_BYTES = 20 * 1024**3


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inspect_directory(path, max_files=MAX_FILES, max_bytes=MAX_BYTES):
    if not path.is_dir() or path.is_symlink():
        raise ValueError('input must be a real directory, not a symlink')
    entries=[]; total=0
    for root, dirs, files in os.walk(path, followlinks=False):
        root=Path(root)
        if any((root / d).is_symlink() for d in dirs):
            raise ValueError('symlink directory is not permitted')
        for name in sorted(files):
            f=root/name
            if f.is_symlink() or not f.is_file():
                raise ValueError('symlink or nonregular file is not permitted')
            size=f.stat().st_size
            total+=size
            if len(entries)>=max_files or total>max_bytes:
                raise ValueError('intake budget exceeded')
            entries.append({'path':f.relative_to(path).as_posix(),'bytes':size,'sha256':sha256_file(f)})
    entries.sort(key=lambda x:x['path'])
    return {'kind':'directory','files':entries,'count':len(entries),'total_uncompressed_bytes':total,'passed':True}


def inspect_zip(path, max_files=MAX_FILES, max_bytes=MAX_BYTES):
    if path.is_symlink() or not path.is_file() or not zipfile.is_zipfile(path):
        raise ValueError('input must be a real ZIP file')
    entries=[]; seen=set(); total=0
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            name=info.filename.replace('\\','/')
            p=PurePosixPath(name)
            if (p.is_absolute() or '..' in p.parts or not name or ':' in p.parts[0] or '\x00' in name):
                raise ValueError('unsafe archive path')
            if info.is_dir():
                continue
            mode=(info.external_attr>>16)
            if stat.S_IFMT(mode)==stat.S_IFLNK:
                raise ValueError('symlink entry is not permitted')
            if name in seen:
                raise ValueError('duplicate archive path')
            seen.add(name)
            total+=info.file_size
            if len(entries)>=max_files or total>max_bytes:
                raise ValueError('intake budget exceeded')
            # ZIP CRC is verified by reading decompressed bytes, without extraction.
            h=hashlib.sha256()
            with z.open(info) as f:
                for block in iter(lambda:f.read(1024*1024),b''):
                    h.update(block)
            entries.append({'path':name,'bytes':info.file_size,'sha256':h.hexdigest()})
    entries.sort(key=lambda x:x['path'])
    return {'kind':'zip','files':entries,'count':len(entries),'total_uncompressed_bytes':total,'passed':True,'archive_sha256':sha256_file(path)}


def inspect(path, max_files=MAX_FILES, max_bytes=MAX_BYTES):
    path=Path(path)
    return inspect_directory(path,max_files,max_bytes) if path.is_dir() else inspect_zip(path,max_files,max_bytes)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('path',type=Path)
    p.add_argument('--max-files',type=int,default=MAX_FILES)
    p.add_argument('--max-bytes',type=int,default=MAX_BYTES)
    a=p.parse_args()
    if a.max_files<1 or a.max_bytes<1:p.error('limits must be positive')
    try:
        print(json.dumps(inspect(a.path,a.max_files,a.max_bytes),indent=2))
    except (OSError,ValueError,zipfile.BadZipFile,RuntimeError) as e:
        print(json.dumps({'passed':False,'error':str(e)}))
        raise SystemExit(1)