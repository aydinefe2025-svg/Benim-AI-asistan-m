#!/usr/bin/env python3
"""Build byte-verifiable offline SPDX CLI ZIP with MIT attribution.

Used only after real CI gate tests pass. Downloads *public* pinned source and
official schema; verifies Git blob hash for every file before packaging.
No user data or credentials are bundled.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import spdx_upstream_acceptance as pins

SCRIPTS=(
    'spdx_upstream_acceptance.py',
    'spdx_validation_pipeline.py',
    'spdx_fixture_matrix_24.py',
    'spdx_source_patch.py',
    'spdx_patched_acceptance.py',
    'spdx_secure_merge_cli.py',
    'spdx_secure_merge_selftest.py',
    'SPDX_SECURE_MERGE_README_TR.md',
)


def build(destination: Path):
    here=Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='cano-spdx-package-') as td:
        directory=Path(td)
        for name in SCRIPTS:
            shutil.copy2(here/name,directory/name)
        for name in ('spdx-acceptance-results.json','spdx-sourcepatch-results.json'):
            shutil.copy2(Path(name),directory/name)
        for source,blob in pins.FILES.items():
            relative='vendor/'+source
            target=directory/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            url=f'{pins.SOURCE_BASE}{pins.UPSTREAM_REPO}/{pins.UPSTREAM_COMMIT}/{source}'
            target.write_bytes(pins.get_pinned(url,blob))
        license_url=f'{pins.SOURCE_BASE}{pins.UPSTREAM_REPO}/{pins.UPSTREAM_COMMIT}/LICENSE'
        (directory/'vendor'/'LICENSE').write_bytes(
            pins.get_pinned(license_url,'1c896def5a8e38519da3ecfa575feedad5234301'))
        schema_path=directory/'vendor/schemas/spdx-schema.json'
        schema_path.parent.mkdir(parents=True,exist_ok=True)
        schema_path.write_bytes(pins.get_pinned(
            f'{pins.SOURCE_BASE}spdx/spdx-spec/{pins.SPDX_REF}/schemas/spdx-schema.json',
            pins.SCHEMA_BLOB))
        records={}
        for p in sorted(directory.rglob('*')):
            if p.is_file():
                records[p.relative_to(directory).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
        metadata={
            'upstream_commit':pins.UPSTREAM_COMMIT,
            'upstream_merger_git_blob':pins.FILES['src/sbom_unifier/merge/merger.py'],
            'official_schema_tag':pins.SPDX_REF,
            'official_schema_git_blob':pins.SCHEMA_BLOB,
            'offline_pinned_vendor':True,
            'source_and_schema_sha256':records,
            'deployed':False,'production_ready':False,
            'ci_run_id':os.environ.get('GITHUB_RUN_ID'),
            'github_head_commit':os.environ.get('GITHUB_SHA'),
        }
        (directory/'MANIFEST.json').write_text(
            json.dumps(metadata,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
        with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for path in sorted(directory.rglob('*')):
                if path.is_file():
                    z.write(path,path.relative_to(directory).as_posix())
        with zipfile.ZipFile(destination) as z:
            if z.testzip() is not None:
                raise AssertionError('bundle CRC failed')
            for name,sha in records.items():
                if hashlib.sha256(z.read(name)).hexdigest()!=sha:
                    raise AssertionError('bundle SHA256 mismatch: '+name)
    print(json.dumps({'bundle':str(destination),'bytes':destination.stat().st_size,
                      'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
                      'manifest_files':len(records),'offline_pinned_sources':len(pins.FILES)}))


if __name__=='__main__':
    build(Path('spdx-secure-pilot.zip'))
