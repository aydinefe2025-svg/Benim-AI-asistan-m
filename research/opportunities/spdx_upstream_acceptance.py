#!/usr/bin/env python3
"""Read-only upstream SBOM/SPDX integration acceptance; synthetic inputs only.

Run: python spdx_upstream_acceptance.py --output acceptance-results.json
Requires Python >=3.13, jsonschema==4.26.0, GitHub raw read access.
Do NOT merge, install or modify the upstream library. MIT upstream source notice applies.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
from urllib.request import Request, urlopen

UPSTREAM_REPO = 'MoriwakiYusuke/sbom-unifier'
UPSTREAM_COMMIT = '521f3b8ee6e301e847f7cb113517ba46831e2b28'
SPDX_REF = 'v2.3.1'
FILES = {
 'src/sbom_unifier/merge/merger.py': 'afce37336f1d76f3e803f8eb4198f006c9125407',
 'src/sbom_unifier/merge/fields.py': 'f7cfa5ed1860c091b9b7dc11ee264b19afdbd772',
 'src/sbom_unifier/merge/utils.py': 'a7968b2150514ffc3a41a8f540ba149eb22e98af',
 'src/sbom_unifier/config.py': '7480a9056cef24f65ecc9b600d0d08119c2af919',
}
SCHEMA_BLOB = '2dc11d1a34268227b63113d788b89efd75b5d2a8'
SOURCE_BASE = 'https://raw.githubusercontent.com/'


def get_pinned(url: str, blob: str, cap: int = 120000) -> bytes:
    req = Request(url, headers={'User-Agent':'CANO-SPDX-read-only-acceptance/1.0'})
    with urlopen(req, timeout=30) as response:
        data = response.read(cap + 1)
    if not data or len(data) > cap:
        raise ValueError(f'empty or oversized source: {url}')
    got = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
    if got != blob:
        raise ValueError(f'Git blob mismatch for {url}: {got} != {blob}')
    return data


def get_sources(tmp: Path):
    for path, blob in FILES.items():
        url = f'{SOURCE_BASE}{UPSTREAM_REPO}/{UPSTREAM_COMMIT}/{path}'
        dst = tmp / path.removeprefix('src/')
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(get_pinned(url, blob))
    for path in [tmp/'sbom_unifier/__init__.py',tmp/'sbom_unifier/merge/__init__.py']:
        path.touch()
    schema_bytes = get_pinned(f'{SOURCE_BASE}spdx/spdx-spec/{SPDX_REF}/schemas/spdx-schema.json', SCHEMA_BLOB)
    (tmp/'spdx-schema-v2.3.1.json').write_bytes(schema_bytes)
    sys.path.insert(0, str(tmp))
    m = importlib.import_module('sbom_unifier.merge.merger')
    return json.loads(schema_bytes),m.merge_sbom


def doc(label: str, pkgs: list[dict], rels: list[dict], refs: list[dict]|None=None):
    d = {'SPDXID':'SPDXRef-DOCUMENT','spdxVersion':'SPDX-2.3','dataLicense':'CC0-1.0',
        'name':label,'documentNamespace':f'https://example.org/spdxdocs/{label}-20261114',
        'creationInfo':{'created':'2026-11-14T08:00:00Z','creators':['Tool: CANO synthetic acceptance']},
        'packages':pkgs,'relationships':rels}
    if refs is not None:d['externalDocumentRefs']=refs
    return d


def pkg(name: str, sid: str, license_name: str='MIT') -> dict:
    return {'name':name,'SPDXID':sid,'downloadLocation':'NOASSERTION',
            'licenseDeclared':license_name,'licenseConcluded':license_name,
            'copyrightText':'NOASSERTION',
            'externalRefs':[{'referenceCategory':'PACKAGE-MANAGER','referenceType':'purl',
                             'referenceLocator':f'pkg:pypi/{name.lower()}@1.0'}]}


def rel(a: str,b: str,t: str) -> dict:
    return {'spdxElementId':a,'relatedSpdxElement':b,'relationshipType':t}


def scenarios():
    main = pkg('Main','SPDXRef-Main')
    lib = pkg('Lib','SPDXRef-Lib')
    leaf = pkg('Leaf','SPDXRef-Leaf')
    base = doc('base',[main,lib],[rel('SPDXRef-DOCUMENT','SPDXRef-Main','DESCRIBES'),
                                  rel('SPDXRef-Main','SPDXRef-Lib','CONTAINS')])
    clean = doc('source-clean',[main,leaf],[rel('SPDXRef-DOCUMENT','SPDXRef-Main','DESCRIBES'),
                                           rel('SPDXRef-Main','SPDXRef-Leaf','DEPENDS_ON')])
    bad_parent = doc('source-bad-parent',[lib,leaf],[rel('SPDXRef-DOCUMENT','SPDXRef-Lib','DESCRIBES'),
                                             rel('SPDXRef-Lib','SPDXRef-Leaf','DEPENDS_ON')])
    license_conflict = doc('source-license',[pkg('Lib','SPDXRef-Lib','Apache-2.0')],
                           [rel('SPDXRef-DOCUMENT','SPDXRef-Lib','DESCRIBES')])
    collision = doc('source-collision',[pkg('Leaf','SPDXRef-Lib')],
                    [rel('SPDXRef-DOCUMENT','SPDXRef-Lib','DESCRIBES')])
    # externalDocumentRefs is structurally valid but no foreign document bytes are supplied;
    # application policy therefore must refuse to attest this case.
    ext = [{'externalDocumentId':'DocumentRef-remote',
            'spdxDocument':'https://example.org/external.spdx.json',
            'checksum':{'algorithm':'SHA1','checksumValue':'0'*40}}]
    external = doc('source-external',[main], [rel('SPDXRef-DOCUMENT','SPDXRef-Main','DESCRIBES')],refs=ext)
    return [
      ('clean',base,clean,'ACCEPT'),
      ('wrong_parent',base,bad_parent,'REJECT'),
      ('license_conflict',base,license_conflict,'REVIEW_REQUIRED'),
      ('id_collision',base,collision,'REJECT'),
      ('unverified_external',base,external,'REJECT'),
    ]


def purl(pkg):
    for ref in pkg.get('externalRefs',[]):
        if ref.get('referenceType')=='purl':return ref.get('referenceLocator')
    return None


def checks(base, source, merged, summary):
    issues=[]
    ids=['SPDXRef-DOCUMENT']+[n['SPDXID'] for group in ('packages','files','snippets') for n in merged.get(group,[])]
    if len(ids)!=len(set(ids)):issues.append('duplicate_spdxid')
    purls=[purl(p) for p in merged.get('packages',[]) if purl(p)]
    if len(purls)!=len(set(purls)):issues.append('duplicate_purl')
    if merged.get('spdxVersion')!='SPDX-2.3':issues.append('wrong_version')
    if merged.get('dataLicense')!='CC0-1.0':issues.append('wrong_data_license')
    for rr in merged.get('relationships',[]):
        for key in ('spdxElementId','relatedSpdxElement'):
            r=rr.get(key)
            if r not in ids and not (isinstance(r,str) and r.startswith('DocumentRef-')):
                issues.append('dangling_relationship')
    # The original function permits conflicts with an annotation; our gate does not.
    if summary['fields_conflict']:issues.append('field_conflict')
    if merged.get('externalDocumentRefs'):issues.append('unverified_external_document')
    original = {(r['spdxElementId'],r['relatedSpdxElement'],r['relationshipType']) for r in base['relationships']}
    source_by_id={p['SPDXID']:purl(p) for p in source.get('packages',[])}
    merged_by_purl={purl(p):p['SPDXID'] for p in merged.get('packages',[]) if purl(p)}
    expected=set(original)
    for rr in source.get('relationships',[]):
        if rr['relationshipType']=='DESCRIBES':continue
        def mapped(s):
            if s=='SPDXRef-DOCUMENT':return s
            return merged_by_purl.get(source_by_id.get(s))
        a,b=mapped(rr['spdxElementId']),mapped(rr['relatedSpdxElement'])
        if a and b:expected.add((a,b,rr['relationshipType']))
    actual={(r['spdxElementId'],r['relatedSpdxElement'],r['relationshipType']) for r in merged['relationships']}
    extra=sorted(actual-expected)
    missing=sorted(expected-actual)
    if extra:issues.append('unexpected_relationship')
    if missing:issues.append('missing_relationship')
    return sorted(set(issues)),extra,missing


def run(out: Path):
    import jsonschema
    with tempfile.TemporaryDirectory(prefix='cano-spdx-upstream-') as d:
        schema,merge = get_sources(Path(d))
        validator=jsonschema.Draft201909Validator(schema)
        cases=[]
        for label,base,source,expected in scenarios():
            # Each scenario starts with isolated synthetic documents.
            base,source=copy.deepcopy(base),copy.deepcopy(source)
            before=copy.deepcopy(base)
            input_issues=[sorted(e.message for e in validator.iter_errors(obj)) for obj in (base,source)]
            if any(input_issues):raise AssertionError(f'invalid input fixture {label}: {input_issues}')
            result=merge(base,source,'CANO-synthetic')
            structural=sorted(e.message for e in validator.iter_errors(base))
            semantic,unexpected,missing=checks(before,source,base,result)
            verdict='REJECT' if structural or any(x!='field_conflict' for x in semantic) else 'REVIEW_REQUIRED' if semantic else 'ACCEPT'
            ok=verdict==expected
            case={'case':label,'expected':expected,'actual':verdict,'passed':ok,
                  'schema_errors':structural,'semantic_issues':semantic,
                  'unexpected_edges':unexpected,'missing_edges':missing,
                  'upstream_merge_summary':result}
            cases.append(case)
            print(json.dumps({'case':label,'passed':ok,'expected':expected,'actual':verdict,
                              'schema_errors':structural,'semantic':semantic,'unexpected':unexpected},ensure_ascii=False))
        data={'tool':'CANO upstream integration acceptance','language':'Python 3.13',
              'upstream_commit':UPSTREAM_COMMIT,'source_blobs':FILES,
              'spdx_schema_tag':SPDX_REF,'spdx_schema_blob':SCHEMA_BLOB,
              'jsonschema_version':jsonschema.__version__ if hasattr(jsonschema,'__version__') else '4.26.0',
              'total':len(cases),'passed':sum(x['passed'] for x in cases),'cases':cases,
              'status':'pass' if all(x['passed'] for x in cases) else 'fail'}
        out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        if data['status']!='pass':raise AssertionError(f"{data['passed']}/{data['total']} acceptance cases")

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('spdx-acceptance-results.json'))
    args=p.parse_args();run(args.output)
