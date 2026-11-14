#!/usr/bin/env python3
"""Real original-source patch acceptance, *not* an output-only normalizer.

Pinned upstream MIT source is modified solely within temporary isolated CI
workspace. No live application, upstream repository, or customer data touched.
"""
from __future__ import annotations
import argparse
import copy
import json
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
import jsonschema
import spdx_upstream_acceptance as reference
from spdx_source_patch import load_patched, patch_merger_bytes


def gate(base: dict, source: dict, merge, validator, label: str):
    # The original merger mutates the first argument. Always work on a private
    # copy and disclose the result only if structural + semantic gates pass.
    before = copy.deepcopy(base)
    working = copy.deepcopy(base)
    source = copy.deepcopy(source)
    input_errors = [sorted(e.message for e in validator.iter_errors(x))
                    for x in (working,source)]
    if any(input_errors):
        return {'label':label,'verdict':'REJECT','input_errors':input_errors,
                'base_unchanged':base==before,'merged':None}
    try:
        summary = merge(working,source,'CANO-pinned-synthetic')
        issues,extra,missing = reference.checks(before,source,working,summary)
        structural = sorted(e.message for e in validator.iter_errors(working))
        severe=[x for x in issues if x!='field_conflict']
        decision=('REJECT' if structural or severe else
                  'REVIEW_REQUIRED' if 'field_conflict' in issues else 'ACCEPT')
        return {'label':label,'verdict':decision,'structural_errors':structural,
                'issues':issues,'extra_relationships':extra,'missing_relationships':missing,
                'original_input_unchanged':base==before,
                'merged':working if decision=='ACCEPT' else None,
                'summary':summary}
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        return {'label':label,'verdict':'REJECT','exception_type':type(e).__name__,
                'original_input_unchanged':base==before,'merged':None}


def run(path: Path):
    negative = []
    for src in [b'not real Python code',b'def merge_transitive_relationships(): pass\n']:
        try:
            patch_merger_bytes(src)
            negative.append(False)
        except ValueError:
            negative.append(True)
    assert all(negative), 'unexpected upstream source silently patched'
    with TemporaryDirectory(prefix='cano-source-patched-') as d:
        schema, patched_merger, patch_metadata = load_patched(Path(d))
        jsonschema.Draft201909Validator.check_schema(schema)
        v=jsonschema.Draft201909Validator(schema)
        rows=[]
        # Crucial change from the old safety *rejection* gate: now actual source
        # level correction makes a formerly wrong-parent source merge ACCEPTED.
        expectations={'clean':'ACCEPT','wrong_parent':'ACCEPT',
                      'license_conflict':'REVIEW_REQUIRED',
                      'id_collision':'REJECT','unverified_external':'REJECT'}
        for label,base,source,_ in reference.scenarios():
            g=gate(base,source,patched_merger.merge_sbom,v,label)
            assert label in expectations
            expected=expectations[label]
            extra_check=True
            if label=='wrong_parent' and g['verdict']=='ACCEPT':
                relationships={(r['spdxElementId'],r['relatedSpdxElement'],r['relationshipType'])
                               for r in g['merged'].get('relationships',[])}
                extra_check=(('SPDXRef-Lib','SPDXRef-Leaf','DEPENDS_ON') in relationships
                            and ('SPDXRef-Main','SPDXRef-Leaf','DEPENDS_ON') not in relationships)
            if g['verdict']=='ACCEPT':
                # Source code should no longer introduce any nested annotation ID.
                extra_check=extra_check and all(
                    'spdxElementId' not in a
                    for group in ('packages','files','snippets')
                    for node in g['merged'].get(group,[])
                    for a in node.get('annotations',[]))
            passed=(g['verdict']==expected and g['original_input_unchanged'] and extra_check)
            rows.append({k:value for k,value in g.items() if k!='merged'} |
                        {'expected':expected,'passed':passed,'graph_assertion':extra_check})
            print(json.dumps({'label':label,'expected':expected,'actual':g['verdict'],
                              'passed':passed,'graph_assertion':extra_check,
                              'structural_errors':g.get('structural_errors',[]),
                              'issues':g.get('issues',[])},ensure_ascii=False))
        # Test a nested annotation with a file conflict to ensure the targeted
        # source patch affects both file and package generated annotations.
        base=reference.doc('file-base',[reference.pkg('Main','SPDXRef-Main')],
                           [reference.rel('SPDXRef-DOCUMENT','SPDXRef-Main','DESCRIBES')])
        base['files']=[{'SPDXID':'SPDXRef-F1','fileName':'./hello.py',
                         'checksums':[{'algorithm':'SHA256','checksumValue':'0'*64}],
                         'licenseConcluded':'MIT','copyrightText':'NOASSERTION'}]
        source=reference.doc('file-src',[reference.pkg('Main','SPDXRef-Main')],
                           [reference.rel('SPDXRef-DOCUMENT','SPDXRef-Main','DESCRIBES')])
        source['files']=[{'SPDXID':'SPDXRef-F2','fileName':'./hello.py',
                         'checksums':[{'algorithm':'SHA256','checksumValue':'0'*64}],
                         'licenseConcluded':'Apache-2.0','copyrightText':'NOASSERTION'}]
        file_gate=gate(base,source,patched_merger.merge_sbom,v,'file_license_conflict')
        file_ok=(file_gate['verdict']=='REVIEW_REQUIRED' and file_gate['original_input_unchanged']
                 and not file_gate.get('structural_errors'))
        rows.append({k:value for k,value in file_gate.items() if k!='merged'} |
                    {'expected':'REVIEW_REQUIRED','passed':file_ok})
        print(json.dumps({'label':'file_license_conflict',
                          'expected':'REVIEW_REQUIRED','actual':file_gate['verdict'],
                          'passed':file_ok,'schema_errors':file_gate.get('structural_errors',[])},
                         ensure_ascii=False))
        data={'run_type':'pinned MIT original source-level patch, Python jsonschema',
              'upstream_commit':reference.UPSTREAM_COMMIT,
              'schema_git_blob':reference.SCHEMA_BLOB,'patch':patch_metadata,
              'python_jsonschema_version':version('jsonschema'),
              'negative_source_shape_controls':negative,
              'total':len(rows),'passed':sum(x['passed'] for x in rows),
              'status':'PASS' if all(x['passed'] for x in rows) else 'FAIL',
              'cases':rows,
              'upstream_git_modified':False,'production_deployed':False}
        path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        if data['status']!='PASS':
            raise AssertionError(f"source patch gate: {data['passed']}/{data['total']}")
        print(f"Source-level patch verified {data['passed']}/{data['total']} cases")


if __name__=='__main__':
    arg=argparse.ArgumentParser()
    arg.add_argument('--output',type=Path,default=Path('spdx-sourcepatch-results.json'))
    run(arg.parse_args().output)
