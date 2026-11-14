#!/usr/bin/env python3
"""Independent fail-closed layer over the original upstream merger output.

Raw upstream output is never rewritten; the SPDX schema normalization is performed
on a copy. A green job means *gate decisions* passed, NOT raw upstream compliance.
"""
from __future__ import annotations
import argparse
import copy
import json
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
import jsonschema
import spdx_upstream_acceptance as original


def normalize_annotations(output: dict):
    normalized = copy.deepcopy(output)
    removed = 0
    for group in ('packages','files','snippets'):
        for node in normalized.get(group, []):
            for annotation in node.get('annotations', []):
                if 'spdxElementId' in annotation:
                    if annotation['spdxElementId'] != node.get('SPDXID'):
                        raise ValueError('nested annotation target mismatch')
                    del annotation['spdxElementId']
                    removed += 1
    for annotation in normalized.get('annotations', []):
        if 'spdxElementId' in annotation:
            if annotation['spdxElementId'] != 'SPDXRef-DOCUMENT':
                raise ValueError('document annotation target mismatch')
            del annotation['spdxElementId']
            removed += 1
    return normalized, removed


def test_normalizer_negative_control():
    bad = {'packages':[{'SPDXID':'SPDXRef-A',
                        'annotations':[{'spdxElementId':'SPDXRef-other'}]}]}
    unchanged = copy.deepcopy(bad)
    try:
        normalize_annotations(bad)
    except ValueError:
        assert bad == unchanged, 'negative test mutated source'
        return
    raise AssertionError('unsafe annotation identity wrongly normalized')


def run(output: Path):
    test_normalizer_negative_control()
    with TemporaryDirectory(prefix='cano-spdx-pinned-') as folder:
        schema, merge = original.get_sources(Path(folder))
        validator = jsonschema.Draft201909Validator(schema)
        receipts = []
        for label, base, source, expected in original.scenarios():
            base, source = copy.deepcopy(base), copy.deepcopy(source)
            before = copy.deepcopy(base)
            input_errors = [sorted(e.message for e in validator.iter_errors(d)) for d in (base,source)]
            if any(input_errors):
                raise AssertionError(f'Invalid input fixture {label}: {input_errors}')
            summary = merge(base,source,'CANO-synthetic')
            raw_schema_errors = sorted(e.message for e in validator.iter_errors(base))
            normalized, removed = normalize_annotations(base)
            normalized_schema_errors = sorted(e.message for e in validator.iter_errors(normalized))
            semantic, extra, missing = original.checks(before,source,normalized,summary)
            verdict = ('REJECT' if normalized_schema_errors or any(i!='field_conflict' for i in semantic)
                       else 'REVIEW_REQUIRED' if semantic else 'ACCEPT')
            case = {'name':label,'expected':expected,'verdict':verdict,'passed':verdict==expected,
                    'raw_upstream_schema_errors':raw_schema_errors,
                    'normalized_schema_errors':normalized_schema_errors,
                    'removed_redundant_annotation_target_fields':removed,
                    'semantic_findings':semantic,'unexpected_edges':extra,'missing_edges':missing,
                    'upstream_summary':summary}
            receipts.append(case)
            print(json.dumps({'name':label,'passed':case['passed'],
                              'verdict':verdict,'raw_schema_error_count':len(raw_schema_errors),
                              'normalized_schema_error_count':len(normalized_schema_errors),
                              'semantic':semantic,'removed_fields':removed},ensure_ascii=False))
        result = {'date':'2026-11-14','test':'original upstream, official schema, separate normalization and safety gate',
                  'upstream_commit':original.UPSTREAM_COMMIT,'upstream_git_blob_sha1':original.FILES,
                  'spdx_schema_tag':original.SPDX_REF,'spdx_git_blob_sha1':original.SCHEMA_BLOB,
                  'python_jsonschema_version':version('jsonschema'),
                  'raw_upstream_schema_compliant':all(not c['raw_upstream_schema_errors'] for c in receipts),
                  'negative_annotation_target_control':'PASS',
                  'total':len(receipts),'passed':sum(c['passed'] for c in receipts),
                  'gate_passed':all(c['passed'] for c in receipts),'cases':receipts}
        output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
        if not result['gate_passed']:
            raise AssertionError(f"Only {result['passed']}/{result['total']} safety gate cases passed")


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('spdx-acceptance-results.json'))
    run(parser.parse_args().output)
