#!/usr/bin/env python3
"""CANO SPDX 2.3 safe local merger — experimental CLI, no cloud upload.

Usage:
  python spdx_secure_merge_cli.py --base base.spdx.json --source source.spdx.json \
      --base-sha256 <trusted-digest> --source-sha256 <trusted-digest> \
      --output merged.spdx.json

Requires Python >=3.13 and jsonschema==4.26.0. With the verified offline
vendor bundle, no network access is needed for the original source/schema. The user-provided SBOM bytes are never uploaded.
SHA256 supplied by the user must come from an *independent trusted manifest*.
A hash alone is not proof of publisher identity or license compliance.
Source MIT (c) 2026 moriwaki: https://github.com/MoriwakiYusuke/sbom-unifier
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory

import jsonschema
import spdx_upstream_acceptance as reference
from spdx_source_patch import load_patched

MAX_FILE_BYTES = 4 * 1024 * 1024


class RejectedInput(ValueError):
    pass


def pairs_no_duplicates(items):
    obj={}
    for k,v in items:
        if k in obj:
            raise RejectedInput(f'duplicate JSON field: {k}')
        obj[k]=v
    return obj


def read_verified_json(path: Path, expected_sha256: str):
    """Read one ordinary local file; reject link/size/metadata drift."""
    if len(expected_sha256)!=64 or any(x not in '0123456789abcdefABCDEF' for x in expected_sha256):
        raise RejectedInput('expected SHA256 must be 64 hexadecimal chars')
    if os.name == 'nt':
        # A Windows CreateFileW handle with FILE_FLAG_OPEN_REPARSE_POINT
        # prevents following a leaf symlink. The GetFileInformationByHandle
        # check also rejects junction/reparse-point and hardlinked inputs.
        from spdx_secure_windows_io import read_single_regular_file
        raw=read_single_regular_file(path,MAX_FILE_BYTES)
    else:
        flags=os.O_RDONLY | getattr(os,'O_NOFOLLOW',0) | getattr(os,'O_CLOEXEC',0)
        flags |= getattr(os,'O_NONBLOCK',0)
        if not hasattr(os,'O_NOFOLLOW'):
            raise RejectedInput('O_NOFOLLOW unavailable: platform unsupported')
        fd=os.open(path,flags)
        try:
            before=os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise RejectedInput('only single-link regular files are allowed')
            if before.st_size<1 or before.st_size>MAX_FILE_BYTES:
                raise RejectedInput('input size outside bounded range')
            chunks=[]
            remaining=MAX_FILE_BYTES+1
            while remaining:
                buf=os.read(fd,min(65536,remaining))
                if not buf:break
                chunks.append(buf)
                remaining-=len(buf)
            raw=b''.join(chunks)
            after=os.fstat(fd)
            if (len(raw)!=before.st_size or len(raw)>MAX_FILE_BYTES
                or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)
                != (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
                raise RejectedInput('input changed while reading')
        finally:
            os.close(fd)
    sha=hashlib.sha256(raw).hexdigest()
    if sha.lower()!=expected_sha256.lower():
        raise RejectedInput('input digest differs from trusted expected SHA256')
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs_no_duplicates)
    except (UnicodeError,json.JSONDecodeError) as e:
        raise RejectedInput('invalid UTF-8 JSON') from e
    if not isinstance(value,dict):
        raise RejectedInput('SPDX document must be a JSON object')
    return value,sha


def input_issues(doc: dict, validator: jsonschema.Draft201909Validator):
    errors=[f'schema: {e.message}' for e in validator.iter_errors(doc)]
    if doc.get('spdxVersion')!='SPDX-2.3':errors.append('unsupported SPDX version')
    if doc.get('dataLicense')!='CC0-1.0':errors.append('unsupported data license')
    if doc.get('externalDocumentRefs'):errors.append('externalDocumentRefs require separately verified foreign bytes')
    ids=['SPDXRef-DOCUMENT']
    purls=[]
    for group in ('packages','files','snippets'):
        for node in doc.get(group,[]):
            sid=node.get('SPDXID')
            if sid in ids:errors.append('duplicate SPDXID in input')
            ids.append(sid)
            if group=='packages':
                purl=reference.purl(node)
                if not purl:errors.append('package missing PURL; identity cannot be mapped')
                elif purl in purls:errors.append('duplicate PURL in input')
                purls.append(purl)
    for rel in doc.get('relationships',[]):
        for field in ('spdxElementId','relatedSpdxElement'):
            dest=rel.get(field)
            if dest not in ids:errors.append('unresolved input relationship endpoint')
    return sorted(set(errors))


def decision(base: dict, source: dict, merge_function, validator):
    """Never modify input dicts; reject incomplete or ambiguous outcomes."""
    pre=input_issues(base,validator)+input_issues(source,validator)
    if pre:
        return 'REJECT',None,sorted(set(pre)),{}
    target=copy.deepcopy(base)
    baseline=copy.deepcopy(base)
    summary=merge_function(target,copy.deepcopy(source),'CANO-verified-local')
    err=[f'schema: {e.message}' for e in validator.iter_errors(target)]
    sem,extra,missing=reference.checks(baseline,source,target,summary)
    all_issues=sorted(set(err+sem))
    if extra:all_issues.append('unexpected relationship graph edges')
    if missing:all_issues.append('missing expected graph edges')
    # Reject output identity collisions and all external references even when
    # a source forgot to declare them. Do not guess foreign document trust.
    if target.get('externalDocumentRefs'):
        all_issues.append('unverified output externalDocumentRefs')
    severe=[x for x in all_issues if x!='field_conflict']
    verdict=('REJECT' if severe else 'REVIEW_REQUIRED' if all_issues else 'ACCEPT')
    return verdict,target if verdict=='ACCEPT' else None,sorted(set(all_issues)),summary


def write_exclusive(output: Path, document: dict):
    raw=(json.dumps(document,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_CLOEXEC',0),0o600)
    completed=False
    try:
        with os.fdopen(fd,'wb',closefd=True) as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        completed=True
    finally:
        if not completed:
            try:output.unlink()
            except FileNotFoundError:pass
    return hashlib.sha256(raw).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--base-sha256',required=True)
    parser.add_argument('--source-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    record={'tool':'CANO SPDX local merge','status':'REJECTED',
            'output_written':False,'upstream_commit':reference.UPSTREAM_COMMIT,
            'schema_tag':reference.SPDX_REF}
    try:
        base,base_sha=read_verified_json(args.base,args.base_sha256)
        source,source_sha=read_verified_json(args.source,args.source_sha256)
        record.update({'base_sha256':base_sha,'source_sha256':source_sha})
        with TemporaryDirectory(prefix='cano-spdx-verified-') as dir:
            schema,mod,patch=load_patched(Path(dir))
            jsonschema.Draft201909Validator.check_schema(schema)
            verdict,result,problems,summary=decision(base,source,mod.merge_sbom,
                jsonschema.Draft201909Validator(schema))
            record.update({'status':verdict,'problems':problems,'summary':summary,
                           'patched_source_sha256':patch['source_level_patch']['patched_sha256'],
                           'source_mode':patch.get('source_mode')})
            if verdict!='ACCEPT':print(json.dumps(record,ensure_ascii=False));return 2
            output=args.output
            if output.resolve() in (args.base.resolve(),args.source.resolve()):
                raise RejectedInput('output must not overwrite source input')
            out_sha=write_exclusive(output,result)
            record.update({'output_written':True,'output_sha256':out_sha,
                           'output_path':str(output)})
            print(json.dumps(record,ensure_ascii=False))
            return 0
    except (RejectedInput,FileNotFoundError,FileExistsError,OSError,ValueError,
            jsonschema.exceptions.SchemaError) as e:
        record.update({'status':'REJECTED','error_type':type(e).__name__,
                       'error':str(e)[:240]})
        print(json.dumps(record,ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
